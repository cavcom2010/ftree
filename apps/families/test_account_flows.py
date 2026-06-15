from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
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
        self.assertContains(response, reverse("password_reset"))
        self.assertContains(response, "Forgot password?")

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
        self.assertIn("Copy and open this single-line reset link:\n\n", message.body)
        self.assertIn("/r/", message.body)
        self.assertNotIn("/accounts/reset/", message.body)
        reset_lines = [line for line in message.body.splitlines() if "/r/" in line]
        self.assertEqual(len(reset_lines), 1)
        self.assertTrue(reset_lines[0].startswith("http://testserver/r/"))
        self.assertNotIn(" ", reset_lines[0])
        self.assertIn("Your username is: reset-user", message.body)
        self.assertNotIn("You're receiving this email", message.body)
        self.assertNotIn("you\u2019ve", message.body)

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
