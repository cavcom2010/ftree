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

    def test_logged_out_navigation_uses_tree_and_single_account_entry(self):
        response = self.client.get("/")

        self.assertContains(response, "data-bottom-tree-link")
        self.assertContains(response, "data-bottom-account-trigger")
        self.assertContains(response, "data-header-account-trigger", count=1)
        self.assertContains(response, 'id="accountSheet"')
        self.assertContains(response, "data-account-login-link")
        self.assertContains(response, "data-account-signup-link")
        self.assertNotContains(response, 'aria-label="Log in"')
        self.assertNotContains(response, 'aria-label="Create account"')
        self.assertNotContains(response, 'data-lucide="log-in"></i>Log in')
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
        self.assertContains(response, "Details")

    def test_tree_page_excludes_homepage_and_social_content(self):
        response = self.client.get("/tree/")

        self.assertNotContains(response, "hero")
        self.assertNotContains(response, "Family Prompt")
        self.assertNotContains(response, "memory-strip")
        self.assertNotContains(response, "Recent Activity")
        self.assertNotContains(response, "bottom-nav")
        self.assertNotContains(response, "desktop-side")
        self.assertNotContains(response, "desktop-panel")

    def test_tree_page_anchor_uses_membership_person(self):
        membership = FamilyMembership.objects.select_related("person").get(user__username="demo")

        self.assertEqual(membership.person.first_name, "David")

        response = self.client.get("/tree/")

        self.assertContains(response, "Centred on David Johnson")
        self.assertContains(response, "David Johnson")
        self.assertContains(response, "Me · Gen 0")

    def test_tree_page_repairs_membership_without_person(self):
        user = User.objects.create_user(username="anchorless")
        family = Family.objects.create(name="Anchorless Family", slug="anchorless", created_by=user)
        person = Person.objects.create(
            family=family,
            first_name="Alex",
            last_name="Stone",
            created_by=user,
        )
        membership = FamilyMembership.objects.create(
            family=family,
            user=user,
            role=FamilyMembership.Role.OWNER,
        )
        self.client.force_login(user)

        response = self.client.get("/tree/")

        self.assertEqual(response.status_code, 200)
        membership.refresh_from_db()
        self.assertEqual(membership.person, person)
        self.assertContains(response, "Centred on Alex Stone")
        self.assertContains(response, "Me · Gen 0")
        self.assertContains(response, "Start your tree")
        self.assertNotContains(response, "Who are you in this family tree?")
        self.assertNotContains(response, "Set Gen 0")

    def test_anchor_chooser_saves_membership_person(self):
        user = User.objects.create_user(username="chooser")
        family = Family.objects.create(name="Chooser Family", slug="chooser-family", created_by=user)
        person = Person.objects.create(
            family=family,
            first_name="Morgan",
            last_name="Tree",
            created_by=user,
        )
        membership = FamilyMembership.objects.create(
            family=family,
            user=user,
            role=FamilyMembership.Role.OWNER,
        )
        self.client.force_login(user)

        response = self.client.post(
            f"/tree/people/{person.id}/set-anchor/",
            {"family": family.slug},
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.person, person)


class SeedDemoMediaCommandTests(TestCase):
    def setUp(self):
        self.media_root = TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media_root.name)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.media_root.cleanup()

    def test_skip_downloads_creates_articles_and_memory_records_idempotently(self):
        call_command("seed_demo_media", "--skip-downloads", verbosity=0)
        call_command("seed_demo_media", "--skip-downloads", verbosity=0)

        family = Family.objects.get(slug="johnson-family")
        expected_memory_count = len(PHOTO_MEMORY_SEEDS) + len(VIDEO_MEMORY_SEEDS)
        expected_story_count = len(STORY_ARTICLE_SEEDS)

        self.assertEqual(Memory.objects.filter(family=family).count(), expected_memory_count)
        self.assertEqual(Story.objects.filter(family=family).count(), expected_story_count)

    def test_requires_pixabay_key_when_downloads_are_enabled(self):
        with patch("apps.core.management.commands.seed_demo_media.config", side_effect=UndefinedValueError("PIXABAY_API_KEY")):
            with self.assertRaises(CommandError):
                call_command("seed_demo_media", verbosity=0)
