from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


class Command(BaseCommand):
    help = "Print a password reset link for an active user."

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

    def handle(self, *args, **options):
        user = self._get_user(options["identifier"])
        base_url = self._base_url(options["base_url"])

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        path = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})

        self.stdout.write(urljoin(f"{base_url}/", path.lstrip("/")))

    def _get_user(self, identifier):
        User = get_user_model()
        username_field = User.USERNAME_FIELD
        username_matches = list(
            User._default_manager.filter(
                **{username_field: identifier},
                is_active=True,
            )
        )
        if username_matches:
            user = username_matches[0]
            if not user.has_usable_password():
                raise CommandError("The matched user does not have a usable password.")
            return user

        email_matches = list(
            User._default_manager.filter(email__iexact=identifier, is_active=True)
        )
        email_matches = [user for user in email_matches if user.has_usable_password()]
        if not email_matches:
            inactive_match_exists = (
                User._default_manager.filter(
                    **{username_field: identifier},
                    is_active=False,
                ).exists()
                or User._default_manager.filter(
                    email__iexact=identifier,
                    is_active=False,
                ).exists()
            )
            if inactive_match_exists:
                raise CommandError(
                    "The matched user is inactive. Verify the email address first with print_email_verification_link."
                )
            raise CommandError("No active user with a usable password matched that identifier.")
        if len(email_matches) > 1:
            raise CommandError(
                "Multiple active users share that email address. Use the username instead."
            )
        return email_matches[0]

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
