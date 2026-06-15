from datetime import timedelta
from hashlib import sha256

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.families.forms import SignupForm
from apps.families.models import EmailVerification

User = get_user_model()

LOGIN_IP_LIMIT = 30
LOGIN_USER_LIMIT = 8
SIGNUP_IP_LIMIT = 5
SIGNUP_EMAIL_LIMIT = 3
RESEND_EMAIL_LIMIT = 3
RATE_LIMIT_WINDOW_SECONDS = 15 * 60
SIGNUP_WINDOW_SECONDS = 60 * 60


class RateLimitedLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = AuthenticationForm

    def post(self, request, *args, **kwargs):
        identifier = (request.POST.get("username") or "").strip().lower() or _client_ip(request)
        if _rate_limited("login-ip", _client_ip(request), LOGIN_IP_LIMIT, RATE_LIMIT_WINDOW_SECONDS) or _rate_limited(
            "login-user", identifier, LOGIN_USER_LIMIT, RATE_LIMIT_WINDOW_SECONDS
        ):
            form = self.get_form()
            form.add_error(None, "Too many sign-in attempts. Please wait a few minutes and try again.")
            response = self.form_invalid(form)
            response.status_code = 429
            return response
        return super().post(request, *args, **kwargs)


@require_http_methods(["GET", "POST"])
def signup(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        email_identifier = (request.POST.get("email") or "").strip().lower() or _client_ip(request)
        if _rate_limited("signup-ip", _client_ip(request), SIGNUP_IP_LIMIT, SIGNUP_WINDOW_SECONDS) or _rate_limited(
            "signup-email", email_identifier, SIGNUP_EMAIL_LIMIT, SIGNUP_WINDOW_SECONDS
        ):
            form.add_error(None, "Too many signup attempts. Please wait and try again.")
            return render(request, "registration/signup.html", {"form": form}, status=429)
        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                user.email = form.cleaned_data["email"]
                user.is_active = False
                user.save()
                verification = _create_email_verification(user)
            _send_email_verification(request, verification)
            return redirect("email_verification_sent")
    else:
        form = SignupForm()
    return render(request, "registration/signup.html", {"form": form})


def email_verification_sent(request):
    return render(request, "registration/email_verification_sent.html")


@require_http_methods(["GET", "POST"])
def resend_email_verification(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        if _rate_limited("resend-email", email or _client_ip(request), RESEND_EMAIL_LIMIT, SIGNUP_WINDOW_SECONDS):
            messages.error(request, "Too many resend attempts. Please wait and try again.")
            return render(request, "registration/email_verification_resend.html", {"email": email}, status=429)
        user = User.objects.filter(email__iexact=email, is_active=False).order_by("id").first()
        if user:
            verification = _create_email_verification(user)
            _send_email_verification(request, verification)
        messages.success(request, "If that email belongs to an unverified account, a new verification link has been sent.")
        return redirect("email_verification_sent")
    return render(request, "registration/email_verification_resend.html")


def verify_email(request, token):
    verification = EmailVerification.objects.select_related("user").filter(token=token).first()
    if not verification:
        return render(
            request,
            "registration/email_verification_invalid.html",
            {"reason": "This verification link is not valid."},
            status=400,
        )
    if verification.is_verified:
        if verification.user.is_active:
            login(request, verification.user, backend="django.contrib.auth.backends.ModelBackend")
        messages.info(request, "This email address has already been verified.")
        return redirect("tree")
    if verification.is_expired:
        return render(
            request,
            "registration/email_verification_invalid.html",
            {"reason": "This verification link has expired. Please request a new one."},
            status=400,
        )

    with transaction.atomic():
        verification.mark_verified()
        user = verification.user
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
    login(request, verification.user, backend="django.contrib.auth.backends.ModelBackend")
    messages.success(request, "Your email address has been verified.")
    return redirect("tree")


def _create_email_verification(user):
    expiry_hours = getattr(settings, "AUTH_EMAIL_VERIFICATION_EXPIRY_HOURS", 24)
    return EmailVerification.objects.create(
        user=user,
        email=user.email.lower(),
        expires_at=timezone.now() + timedelta(hours=expiry_hours),
    )


def _send_email_verification(request, verification):
    verification_url = request.build_absolute_uri(reverse("email_verify", args=[verification.token]))
    subject = "Verify your HeritageTree email address"
    message = render_to_string(
        "registration/email_verification_email.txt",
        {
            "verification": verification,
            "verification_url": verification_url,
        },
    )
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [verification.email],
        fail_silently=False,
    )


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _rate_limited(scope, identifier, limit, window_seconds):
    key = _rate_key(scope, identifier)
    current = cache.get(key, 0)
    if current >= limit:
        return True
    if current:
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window_seconds)
    else:
        cache.add(key, 1, timeout=window_seconds)
    return False


def _rate_key(scope, identifier):
    digest = sha256(str(identifier).encode("utf-8")).hexdigest()
    return f"auth-rate:{scope}:{digest}"
