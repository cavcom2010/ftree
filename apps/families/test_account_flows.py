from datetime import timedelta
from io import StringIO
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone

from apps.families.models import EmailVerification, Family, FamilyMembership
from apps.people.models import Person

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["testserver"], EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountFlowTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_login_form_uses_styled_auth_fields(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "auth-card")
        self.assertContains(response, "auth-form")
        self.assertContains(response, 'class="auth-field"', count=2)
        self.assertContains(response, 'id="id_username"')
        self.assertContains(response, 'id="id_password"')
        self.assertContains(response, 'autocomplete="username"')
        self.assertContains(response, 'autocomplete="current-password"')
        self.assertContains(response, reverse("password_reset"))
        self.assertContains(response, "Forgot password?")

    @override_settings(SESSION_COOKIE_AGE=60 * 60 * 24 * 14, SESSION_EXPIRE_AT_BROWSER_CLOSE=False)
    def test_login_sets_persistent_session_cookie_and_survives_refresh(self):
        User.objects.create_user(username="session-user", email="session@example.com", password="StrongPass123!")

        response = self.client.post(
            reverse("login"),
            {"username": "session-user", "password": "StrongPass123!"},
        )

        self.assertEqual(response.status_code, 302)
        session_cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(int(session_cookie["max-age"]), settings.SESSION_COOKIE_AGE)
        self.assertTrue(session_cookie["expires"])

        home_response = self.client.get("/")
        tree_response = self.client.get(reverse("tree"))

        self.assertEqual(home_response.status_code, 200)
        self.assertEqual(tree_response.status_code, 200)
        self.assertTrue(home_response.wsgi_request.user.is_authenticated)
        self.assertTrue(tree_response.wsgi_request.user.is_authenticated)

    def test_signup_form_uses_styled_auth_fields(self):
        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "auth-card")
        self.assertContains(response, "auth-form")
        self.assertContains(response, 'class="auth-field"', count=4)
        self.assertContains(response, 'name="website"', count=1)

    def test_resend_verification_form_uses_styled_auth_field(self):
        response = self.client.get(reverse("email_verification_resend"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "auth-card")
        self.assertContains(response, "auth-form")
        self.assertContains(response, 'class="auth-field"', count=1)
        self.assertContains(response, 'id="id_email"')

    def test_password_reset_form_uses_styled_auth_field(self):
        response = self.client.get(reverse("password_reset"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "auth-card")
        self.assertContains(response, "auth-form")
        self.assertContains(response, 'class="auth-field"', count=1)
        self.assertContains(response, 'id="id_email"')

    def test_password_reset_email_uses_copy_friendly_template(self):
        User.objects.create_user(username="reset-user", email="reset@example.com", password="OldPass123!")

        response = self.client.post(reverse("password_reset"), {"email": "reset@example.com"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Reset your HeritageTree password")
        self.assertIn("Copy and open this reset link:\n\n", message.body)
        self.assertIn("/accounts/reset/", message.body)
        self.assertIn("Your username is: reset-user", message.body)
        self.assertNotIn("You're receiving this email", message.body)
        self.assertNotIn("you\u2019ve", message.body)

    @override_settings(DEBUG=True, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_password_reset_done_shows_local_development_shortcut_for_console_email(self):
        User.objects.create_user(username="reset-user", email="reset@example.com", password="OldPass123!")

        response = self.client.post(reverse("password_reset"), {"email": "reset@example.com"}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Local development shortcut")
        self.assertContains(response, "Open password reset page")
        self.assertContains(response, "/accounts/reset/")
        self.assertContains(response, "data-local-reset-link")

    def test_password_reset_confirm_form_uses_styled_auth_fields(self):
        user = User.objects.create_user(username="reset-user", email="reset@example.com", password="OldPass123!")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        response = self.client.get(reverse("password_reset_confirm", args=[uid, token]), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "auth-card")
        self.assertContains(response, "auth-form")
        self.assertContains(response, 'class="auth-field"', count=2)
        self.assertContains(response, 'id="id_new_password1"')
        self.assertContains(response, 'id="id_new_password2"')

    def test_print_password_reset_link_command_outputs_valid_reset_url(self):
        User.objects.create_user(username="reset-user", email="reset@example.com", password="OldPass123!")
        output = StringIO()

        call_command(
            "print_password_reset_link",
            "reset-user",
            base_url="https://ftree.example",
            stdout=output,
        )

        reset_url = output.getvalue().strip()
        parsed_url = urlparse(reset_url)
        response = self.client.get(parsed_url.path, follow=True)

        self.assertEqual(parsed_url.scheme, "https")
        self.assertEqual(parsed_url.netloc, "ftree.example")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_new_password1"')

    def test_signup_creates_inactive_user_and_verification_record(self):
        with self.assertLogs("apps.families.auth_views", level="WARNING") as captured:
            response = self.client.post(
                reverse("signup"),
                {
                    "username": "newuser",
                    "email": "new@example.com",
                    "password1": "StrongPass123!",
                    "password2": "StrongPass123!",
                    "website": "",
                },
            )

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="newuser")
        self.assertFalse(user.is_active)
        self.assertEqual(EmailVerification.objects.filter(user=user).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("HeritageTree verification URL for new@example.com:", captured.output[0])
        self.assertIn("/accounts/verify/", captured.output[0])

    def test_email_verification_activates_user(self):
        user = User.objects.create_user(username="inactive", email="inactive@example.com", is_active=False)
        verification = EmailVerification.objects.create(
            user=user,
            email=user.email,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.get(reverse("email_verify", args=[verification.token]))

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        verification.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertIsNotNone(verification.verified_at)

    def test_tree_does_not_show_unowned_family_slug(self):
        owner = User.objects.create_user(username="owner", email="owner@example.com")
        outsider = User.objects.create_user(username="outsider", email="outsider@example.com")
        private_family = Family.objects.create(name="Private Family", slug="private-family", created_by=owner)
        private_person = Person.objects.create(
            family=private_family,
            first_name="Private",
            last_name="Person",
            created_by=owner,
        )
        FamilyMembership.objects.create(family=private_family, user=owner, person=private_person, role=FamilyMembership.Role.OWNER)
        outsider_family = Family.objects.create(name="Outsider Family", slug="outsider-family", created_by=outsider)
        outsider_person = Person.objects.create(
            family=outsider_family,
            first_name="Outsider",
            last_name="Person",
            created_by=outsider,
        )
        FamilyMembership.objects.create(
            family=outsider_family,
            user=outsider,
            person=outsider_person,
            role=FamilyMembership.Role.OWNER,
        )
        self.client.force_login(outsider)

        response = self.client.get(f"{reverse('tree')}?family={private_family.slug}")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Private Person")
