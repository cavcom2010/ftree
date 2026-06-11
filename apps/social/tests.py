from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.families.models import Family
from apps.social.models import Reaction
from apps.stories.models import Story

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["testserver"])
class ReactionViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="secret")
        self.family = Family.objects.create(name="Test Family", slug="test-family")
        self.story = Story.objects.create(
            family=self.family,
            title="Family story",
            body="A story",
            author=self.user,
        )
        self.client.force_login(self.user)

    def test_invalid_reaction_type_is_rejected(self):
        response = self.client.post(f"/react/story/{self.story.id}/invalid/")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Reaction.objects.exists())

    def test_base_template_exposes_csrf_header_for_htmx_posts(self):
        client = Client(enforce_csrf_checks=True)

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", client.cookies)
        self.assertContains(response, "hx-headers")
