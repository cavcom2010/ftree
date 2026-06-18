from datetime import timedelta
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from django.utils import timezone

from apps.families.models import EmailVerification


class Command(BaseCommand):
    help = "Print an email verification link for an inactive user."

    def add_arguments(self, parser):
        parser.add_argument(
            "identifier",
            help="Username or email address for the account.",
        )
        parser.add_argument(
            "--base-url",
            default="",
            help="Absolute site URL to use, for example https://ftree.calvinmazhindu.dev.",
        )
        parser.add_argument(
            "--renew",
            action="store_true",
            help="Create a fresh verification link if the existing one has expired.",
        )

    def handle(self, *args, **options):
        user = self._get_user(options["identifier"])
        if user.is_active:
            raise CommandError(
                "The matched user is already active. Use print_password_reset_link instead."
            )
        if not user.email:
            raise CommandError("The matched user does not have an email address.")

        verification = self._get_verification(user, renew=options["renew"])
        base_url = self._base_url(options["base_url"])
        path = reverse("email_verify", args=[verification.token])

        self.stdout.write(urljoin(f"{base_url}/", path.lstrip("/")))

    def _get_user(self, identifier):
        User = get_user_model()
        username_field = User.USERNAME_FIELD
        username_matches = list(
            User._default_manager.filter(**{username_field: identifier})
        )
        if username_matches:
            return username_matches[0]

        email_matches = list(User._default_manager.filter(email__iexact=identifier))
        if not email_matches:
            raise CommandError("No user matched that identifier.")
        if len(email_matches) > 1:
            raise CommandError(
                "Multiple users share that email address. Use the username instead."
            )
        return email_matches[0]

    def _get_verification(self, user, renew):
        now = timezone.now()
        verification = (
            EmailVerification.objects.filter(
                user=user,
                verified_at__isnull=True,
                expires_at__gt=now,
            )
            .order_by("-created_at")
            .first()
        )
        if verification:
            return verification
        if not renew:
            raise CommandError("No current verification link exists. Re-run with --renew.")

        expiry_hours = getattr(settings, "AUTH_EMAIL_VERIFICATION_EXPIRY_HOURS", 24)
        return EmailVerification.objects.create(
            user=user,
            email=user.email.lower(),
            expires_at=now + timedelta(hours=expiry_hours),
        )

    def _base_url(self, value):
        if value:
            return value.rstrip("/")

        trusted_origins = [
            origin.rstrip("/")
            for origin in getattr(settings, "CSRF_TRUSTED_ORIGINS", [])
            if origin.startswith(("http://", "https://"))
        ]
        if trusted_origins:
            return trusted_origins[0]

        allowed_hosts = [
            host
            for host in getattr(settings, "ALLOWED_HOSTS", [])
            if host and host not in {"*", "localhost", "127.0.0.1"}
        ]
        if allowed_hosts:
            return f"https://{allowed_hosts[0]}"

        raise CommandError("Pass --base-url, for example --base-url https://example.com.")
