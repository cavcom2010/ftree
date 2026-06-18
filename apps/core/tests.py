import json
from datetime import date
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
from apps.prompts.models import FamilyPrompt
from apps.social.models import Activity
from apps.stories.models import Story


@override_settings(ALLOWED_HOSTS=["testserver"])
class HomepageShellTests(TestCase):
    def _login_demo_as_regular_user(self):
        call_command("seed_demo_family", verbosity=0)
        user = User.objects.get(username="demo")
        user.is_staff = False
        user.is_superuser = False
        user.save(update_fields=["is_staff", "is_superuser"])
        self.client.force_login(user)
        return user

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
        self._login_demo_as_regular_user()

        response = self.client.get("/")

        self.assertContains(response, "data-bottom-tree-link")
        self.assertContains(response, 'href="/memories/"')
        self.assertContains(response, 'aria-label="Connect"')
        self.assertContains(response, 'href="/people/create/"')
        self.assertNotContains(response, "data-bottom-account-trigger")
        self.assertNotContains(response, 'id="accountSheet"')

    def test_authenticated_homepage_uses_real_header_and_connect_links(self):
        self._login_demo_as_regular_user()

        response = self.client.get("/")

        self.assertContains(response, 'aria-label="Search tree"')
        self.assertContains(response, 'aria-label="Create family entry"')
        self.assertContains(response, 'class="add-main" href="/tree/" aria-label="Connect"')
        self.assertNotContains(response, "data-tree-search-trigger")
        self.assertNotContains(response, "data-create-sheet-trigger")
        self.assertNotContains(response, "Create menu is available from the tree homepage")
        self.assertNotContains(response, "Search is available from the tree homepage")

    def test_authenticated_homepage_relative_actions_open_anchor_sheets(self):
        user = self._login_demo_as_regular_user()
        anchor = FamilyMembership.objects.select_related("person").get(user=user).person

        response = self.client.get("/")

        for relation_type in ("parent", "partner", "child", "sibling"):
            self.assertContains(
                response,
                f'hx-get="/tree/people/{anchor.id}/invite-relative/{relation_type}/"',
            )
        self.assertContains(response, 'hx-target="#global-sheet"')
        self.assertContains(response, f'hx-get="/people/{anchor.id}/edit-name/"')

    def test_authenticated_homepage_prompt_loads_prompt_endpoint(self):
        user = self._login_demo_as_regular_user()
        family = FamilyMembership.objects.get(user=user).family
        FamilyPrompt.objects.update_or_create(
            family=family,
            active_date=date.today(),
            defaults={"question": "What should we preserve today?"},
        )
        response = self.client.get("/")
        prompt_response = self.client.get("/prompts/current/")

        self.assertContains(response, 'hx-get="/prompts/current/"')
        self.assertContains(prompt_response, "What should we preserve today?")
        self.assertContains(prompt_response, "/prompts/")
        self.assertContains(prompt_response, "/answer/")

    def test_authenticated_homepage_activity_and_memory_cards_are_real_actions(self):
        user = self._login_demo_as_regular_user()
        family = FamilyMembership.objects.get(user=user).family
        person = Person.objects.filter(family=family).first()
        Activity.objects.create(
            family=family,
            actor=user,
            activity_type=Activity.Type.PERSON_ADDED,
            message="Added a test relative",
            person=person,
        )
        response = self.client.get("/")

        self.assertContains(response, f'hx-get="/people/{person.id}/drawer/"')
        self.assertContains(response, 'href="/memories/"')
        self.assertNotContains(response, "Answer sheet opened")
        self.assertNotContains(response, "Shared with family")


@override_settings(ALLOWED_HOSTS=["testserver"])
class TreePageTests(TestCase):
    def setUp(self):
        call_command("seed_demo_family", verbosity=0)
        self.demo_user = User.objects.get(username="demo")
        self.demo_user.is_staff = False
        self.demo_user.is_superuser = False
        self.demo_user.save(update_fields=["is_staff", "is_superuser"])
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
        self.assertEqual(self._tree_data(response), {"people": [], "root_id": None})

    def test_staff_with_personal_membership_still_sees_global_family_picker(self):
        staff = User.objects.create_user(
            username="staff-with-tree",
            email="staff-with-tree@example.com",
            is_staff=True,
        )
        admin_family = Family.objects.create(
            name="Admin's Family Tree",
            slug="admin-family-tree",
            created_by=staff,
        )
        admin_person = Person.objects.create(
            family=admin_family,
            first_name="Admin",
            last_name="Family",
            created_by=staff,
        )
        FamilyMembership.objects.create(
            family=admin_family,
            user=staff,
            person=admin_person,
            role=FamilyMembership.Role.OWNER,
        )
        family_count = Family.objects.count()
        person_count = Person.objects.count()
        self.client.force_login(staff)

        response = self.client.get("/tree/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin view")
        self.assertContains(response, "Choose a family tree")
        self.assertContains(response, "Johnson Family")
        self.assertNotContains(response, "Admin&#x27;s Family Tree")
        self.assertEqual(Family.objects.count(), family_count)
        self.assertEqual(Person.objects.count(), person_count)
        self.assertEqual(self._tree_data(response), {"people": [], "root_id": None})

    def test_staff_can_explicitly_open_personal_membership_tree(self):
        staff = User.objects.create_user(
            username="staff-own-tree",
            email="staff-own-tree@example.com",
            is_staff=True,
        )
        admin_family = Family.objects.create(
            name="Admin's Family Tree",
            slug="staff-own-family-tree",
            created_by=staff,
        )
        admin_person = Person.objects.create(
            family=admin_family,
            first_name="Admin",
            last_name="Family",
            created_by=staff,
        )
        FamilyMembership.objects.create(
            family=admin_family,
            user=staff,
            person=admin_person,
            role=FamilyMembership.Role.OWNER,
        )
        self.client.force_login(staff)

        response = self.client.get(f"/tree/?family={admin_family.slug}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin&#x27;s Family Tree")
        self.assertContains(response, "Admin Family · Gen 0")
        tree_data = self._tree_data(response)
        self.assertEqual(len(tree_data["people"]), 1)
        self.assertEqual(tree_data["root_id"], str(admin_person.id))

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

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/tree/")
        self.assertEqual(Family.objects.count(), family_count)
        self.assertEqual(Person.objects.count(), person_count)
        self.assertFalse(FamilyMembership.objects.filter(user=staff).exists())

    def test_staff_tree_json_without_family_returns_empty_tree(self):
        staff = User.objects.create_user(
            username="tree-json-staff",
            email="tree-json-staff@example.com",
            is_staff=True,
        )
        admin_family = Family.objects.create(
            name="Admin's Family Tree",
            slug="tree-json-admin-family-tree",
            created_by=staff,
        )
        admin_person = Person.objects.create(
            family=admin_family,
            first_name="Admin",
            last_name="Family",
            created_by=staff,
        )
        FamilyMembership.objects.create(
            family=admin_family,
            user=staff,
            person=admin_person,
            role=FamilyMembership.Role.OWNER,
        )
        self.client.force_login(staff)

        response = self.client.get("/tree/json/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"people": [], "root_id": None})

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
        self.assertContains(response, "Gen 0")
        self.assertNotContains(response, "Start your tree")
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

        self.assertEqual(response.status_code, 302)
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
