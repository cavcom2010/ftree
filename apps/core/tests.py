from tempfile import TemporaryDirectory
from unittest.mock import patch

from decouple import UndefinedValueError
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.core.management.commands.seed_demo_media import (
    PHOTO_MEMORY_SEEDS,
    STORY_ARTICLE_SEEDS,
    VIDEO_MEMORY_SEEDS,
)
from apps.families.models import Family, FamilyMembership
from apps.memories.models import Memory
from apps.people.models import Person
from apps.stories.models import Story


@override_settings(ALLOWED_HOSTS=["testserver"])
class HomepageShellTests(TestCase):
    def test_homepage_returns_http_200(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

    def test_homepage_contains_tree_canvas(self):
        response = self.client.get("/")

        self.assertContains(response, 'id="tree"')

    def test_homepage_contains_generation_sections(self):
        response = self.client.get("/")

        self.assertContains(response, "gen-band")
        self.assertContains(response, "Generation 1")

    def test_homepage_contains_memory_rails_below_tree(self):
        response = self.client.get("/")
        content = response.content.decode()

        self.assertContains(response, "memory-strip")
        self.assertLess(content.index('id="tree"'), content.index("memory-strip"))

    def test_logged_out_navigation_uses_direct_auth_links(self):
        response = self.client.get("/")

        self.assertContains(response, "data-bottom-tree-link")
        self.assertContains(response, 'href="/accounts/login/"')
        self.assertContains(response, 'href="/accounts/signup/"')
        self.assertNotContains(response, "data-bottom-account-trigger")
        self.assertNotContains(response, "data-header-account-trigger")
        self.assertNotContains(response, "data-account-sheet-trigger")
        self.assertNotContains(response, 'id="accountSheet"')
        self.assertNotContains(response, "data-account-login-link")
        self.assertNotContains(response, "data-account-signup-link")
        self.assertNotContains(response, 'data-lucide="user-plus"></i>Sign up')

    def test_authenticated_navigation_keeps_app_nav_without_account_sheet(self):
        call_command("seed_demo_family", verbosity=0)
        self.client.force_login(User.objects.get(username="demo"))

        response = self.client.get("/")

        self.assertContains(response, "data-bottom-tree-link")
        self.assertContains(response, 'href="/memories/"')
        self.assertContains(response, 'aria-label="Connect"')
        self.assertContains(response, 'href="/people/create/"')
        self.assertNotContains(response, "data-bottom-account-trigger")
        self.assertNotContains(response, 'id="accountSheet"')


@override_settings(ALLOWED_HOSTS=["testserver"])
class TreePageTests(TestCase):
    def setUp(self):
        call_command("seed_demo_family", verbosity=0)
        self.demo_user = User.objects.get(username="demo")
        self.client.force_login(self.demo_user)

    def test_tree_page_requires_login(self):
        self.client.logout()

        response = self.client.get("/tree/")

        self.assertEqual(response.status_code, 302)

    def test_tree_page_creates_starter_tree_for_new_signed_in_user(self):
        user = User.objects.create_user(
            username="newtreeuser",
            email="newtreeuser@example.com",
            first_name="New",
            last_name="User",
        )
        self.client.force_login(user)

        response = self.client.get("/tree/")

        self.assertEqual(response.status_code, 200)
        membership = FamilyMembership.objects.select_related("family", "person").get(user=user)
        self.assertEqual(membership.role, FamilyMembership.Role.OWNER)
        self.assertEqual(membership.person.first_name, "New")
        self.assertEqual(membership.person.last_name, "User")
        self.assertEqual(membership.person.family, membership.family)
        self.assertContains(response, "New&#x27;s Family Tree")
        self.assertContains(response, "Me · Gen 0")
        self.assertContains(response, "Start your tree")
        self.assertContains(response, "You are Gen 0. Build your first family links.")
        self.assertContains(response, "Add parent")
        self.assertContains(response, "Add partner")
        self.assertContains(response, "Add child")

    def test_tree_page_returns_http_200(self):
        response = self.client.get("/tree/")

        self.assertEqual(response.status_code, 200)

    def test_tree_page_contains_tree_canvas(self):
        response = self.client.get("/tree/")

        self.assertContains(response, 'id="tree-canvas"')
        self.assertContains(response, 'data-tree-page')

    def test_tree_page_contains_relative_generation_rows(self):
        response = self.client.get("/tree/")

        self.assertContains(response, "Gen -2")
        self.assertContains(response, "Gen -1")
        self.assertContains(response, "Gen 0")
        self.assertContains(response, "Gen +1")

    def test_tree_page_has_independent_horizontal_scroll_rows(self):
        response = self.client.get("/tree/")

        self.assertContains(response, 'data-tree-row-track', count=4)
        self.assertContains(response, 'data-generation-row="Gen 0"')

    def test_tree_page_contains_reveal_drawer_pills(self):
        response = self.client.get("/tree/")
        self.assertContains(response, "Parents")
        self.assertContains(response, "Partners")
        self.assertContains(response, "Children")
        self.assertContains(response, "Siblings")


@override_settings(ALLOWED_HOSTS=["testserver"])
class SeedDemoMediaCommandTests(TestCase):
    def test_skip_downloads_creates_articles_and_memory_records_idempotently(self):
        call_command("seed_demo_media", skip_downloads=True, verbosity=0)
        family = Family.objects.get(slug="mazhindu-demo")
        expected_memory_count = len(PHOTO_MEMORY_SEEDS) + len(VIDEO_MEMORY_SEEDS)
        expected_story_count = 9

        self.assertEqual(Memory.objects.filter(family=family).count(), expected_memory_count)
        self.assertEqual(Story.objects.filter(family=family).count(), expected_story_count)

        call_command("seed_demo_media", skip_downloads=True, verbosity=0)

        self.assertEqual(Memory.objects.filter(family=family).count(), expected_memory_count)
        self.assertEqual(Story.objects.filter(family=family).count(), expected_story_count)

    def test_download_failure_raises_command_error(self):
        with TemporaryDirectory() as tmpdir:
            with patch("apps.core.management.commands.seed_demo_media.requests.get") as mocked_get:
                mocked_get.side_effect = UndefinedValueError("PIXABAY_API_KEY not set")

                with self.assertRaises(CommandError):
                    call_command("seed_demo_media", media_root=tmpdir, verbosity=0)
