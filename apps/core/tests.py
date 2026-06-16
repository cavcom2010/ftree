import json
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

    def _tree_data(self, response):
        return json.loads(response.context["tree_json"])

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
        self.assertContains(response, "New User · Gen 0")
        self.assertContains(response, 'data-create-sheet-trigger')
        self.assertContains(response, "Add to the family tree")
        self.assertContains(response, "Choose a person in the tree")

    def test_staff_without_membership_sees_family_picker_without_starter_tree(self):
        staff = User.objects.create_user(
            username="tree-staff",
            email="tree-staff@example.com",
            is_staff=True,
        )
        family_count = Family.objects.count()
        person_count = Person.objects.count()
        self.client.force_login(staff)

        response = self.client.get("/tree/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin view")
        self.assertContains(response, "Choose a family tree")
        self.assertContains(response, "Johnson Family")
        self.assertEqual(Family.objects.count(), family_count)
        self.assertEqual(Person.objects.count(), person_count)
        self.assertFalse(FamilyMembership.objects.filter(user=staff).exists())

    def test_staff_can_view_selected_family_read_only_without_membership(self):
        staff = User.objects.create_user(
            username="tree-staff-viewer",
            email="tree-staff-viewer@example.com",
            is_staff=True,
        )
        self.client.force_login(staff)

        response = self.client.get("/tree/?family=johnson-family")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Johnson Family")
        self.assertContains(response, "All families")
        self.assertContains(response, "Robert Johnson · Gen 0")
        self.assertNotContains(response, "Start your tree")
        self.assertNotContains(response, 'data-create-sheet-trigger')
        tree_data = self._tree_data(response)
        self.assertTrue(tree_data["people"])
        self.assertFalse(any(person["can_add_relative"] for person in tree_data["people"]))
        self.assertFalse(FamilyMembership.objects.filter(user=staff).exists())

    def test_staff_can_choose_anchor_in_selected_family(self):
        staff = User.objects.create_user(
            username="tree-staff-anchor",
            email="tree-staff-anchor@example.com",
            is_staff=True,
        )
        anchor = Person.objects.get(family__slug="johnson-family", first_name="Robert")
        self.client.force_login(staff)

        response = self.client.get(f"/tree/?family=johnson-family&anchor={anchor.id}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Robert Johnson · Gen 0")
        self.assertContains(response, 'aria-current="true"')

    def test_staff_homepage_without_membership_does_not_create_starter_tree(self):
        staff = User.objects.create_user(
            username="home-staff",
            email="home-staff@example.com",
            is_staff=True,
        )
        family_count = Family.objects.count()
        person_count = Person.objects.count()
        self.client.force_login(staff)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Family.objects.count(), family_count)
        self.assertEqual(Person.objects.count(), person_count)
        self.assertFalse(FamilyMembership.objects.filter(user=staff).exists())

    def test_regular_non_member_cannot_view_other_family_by_slug(self):
        user = User.objects.create_user(
            username="regular-tree-user",
            email="regular-tree-user@example.com",
            first_name="Regular",
            last_name="User",
        )
        self.client.force_login(user)

        response = self.client.get("/tree/?family=johnson-family")

        self.assertEqual(response.status_code, 200)
        membership = FamilyMembership.objects.select_related("family").get(user=user)
        self.assertNotEqual(membership.family.slug, "johnson-family")
        self.assertContains(response, "Regular&#x27;s Family Tree")
        self.assertNotContains(response, "Johnson Family")

    def test_tree_page_returns_http_200(self):
        response = self.client.get("/tree/")

        self.assertEqual(response.status_code, 200)

    def test_tree_page_contains_tree_canvas(self):
        response = self.client.get("/tree/")

        self.assertContains(response, 'id="tree-canvas"')
        self.assertContains(response, 'data-tree-page')

    def test_tree_page_contains_relative_generation_rows(self):
        response = self.client.get("/tree/")

        tree_data = self._tree_data(response)
        generations = {person["generation"] for person in tree_data["people"]}
        self.assertIn(0, generations)
        self.assertLess(min(generations), 0)
        self.assertGreater(max(generations), 0)

    def test_tree_page_has_independent_horizontal_scroll_rows(self):
        response = self.client.get("/tree/")

        self.assertContains(response, 'id="tree-svg"')
        self.assertContains(response, 'id="labels-container"')
        self.assertContains(response, 'id="nodes-container"')
        self.assertContains(response, 'data-zoom-fit')

    def test_tree_page_contains_reveal_drawer_pills(self):
        response = self.client.get("/tree/")
        self.assertContains(response, "Parents")
        self.assertContains(response, "Partner")
        self.assertContains(response, "Children")
        self.assertContains(response, "Siblings")


@override_settings(ALLOWED_HOSTS=["testserver"])
class SeedDemoMediaCommandTests(TestCase):
    def test_skip_downloads_creates_articles_and_memory_records_idempotently(self):
        call_command("seed_demo_media", skip_downloads=True, verbosity=0)
        family = Family.objects.get(slug="johnson-family")
        expected_memory_count = len(PHOTO_MEMORY_SEEDS) + len(VIDEO_MEMORY_SEEDS)
        expected_story_count = 3 + len(STORY_ARTICLE_SEEDS)

        self.assertEqual(Memory.objects.filter(family=family).count(), expected_memory_count)
        self.assertEqual(Story.objects.filter(family=family).count(), expected_story_count)

        call_command("seed_demo_media", skip_downloads=True, verbosity=0)

        self.assertEqual(Memory.objects.filter(family=family).count(), expected_memory_count)
        self.assertEqual(Story.objects.filter(family=family).count(), expected_story_count)

    def test_missing_pixabay_api_key_raises_command_error(self):
        with patch("apps.core.management.commands.seed_demo_media.config") as mocked_config:
            mocked_config.side_effect = UndefinedValueError("PIXABAY_API_KEY not set")

            with self.assertRaisesMessage(CommandError, "PIXABAY_API_KEY is required"):
                call_command("seed_demo_media", verbosity=0)
