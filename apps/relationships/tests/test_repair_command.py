from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.families.models import Family
from apps.people.models import Person
from apps.relationships.models import Relationship

User = get_user_model()


class RepairSiblingParentLinksTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="secret",
        )
        self.family = Family.objects.create(
            name="Repair Family", slug="repair-family", created_by=self.owner
        )
        self.father = Person.objects.create(
            family=self.family,
            first_name="Father",
            last_name="Repair",
            created_by=self.owner,
        )
        self.mother = Person.objects.create(
            family=self.family,
            first_name="Mother",
            last_name="Repair",
            created_by=self.owner,
        )
        self.child_one = Person.objects.create(
            family=self.family,
            first_name="Child",
            last_name="One",
            created_by=self.owner,
        )
        self.child_two = Person.objects.create(
            family=self.family,
            first_name="Child",
            last_name="Two",
            created_by=self.owner,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.father,
            to_person=self.child_one,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.mother,
            to_person=self.child_one,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.child_one,
            to_person=self.child_two,
            relationship_type=Relationship.Type.SIBLING,
        )

    def _call_command(self, *args, **kwargs):
        out = StringIO()
        err = StringIO()
        call_command("repair_sibling_parent_links", *args, stdout=out, stderr=err, **kwargs)
        return out.getvalue(), err.getvalue()

    def test_dry_run_shows_missing_links_without_creating(self):
        out, _ = self._call_command("--family", self.family.slug, "--dry-run")

        self.assertIn("Would create", out)
        self.assertEqual(
            Relationship.objects.filter(
                family=self.family,
                to_person=self.child_two,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).count(),
            0,
        )

    def test_command_creates_missing_parent_links_for_orphan_sibling(self):
        out, _ = self._call_command("--family", self.family.slug)

        self.assertIn("Creating", out)
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=self.father,
                to_person=self.child_two,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=self.mother,
                to_person=self.child_two,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )

    def test_default_mode_skips_pair_when_both_have_parents(self):
        Relationship.objects.create(
            family=self.family,
            from_person=self.father,
            to_person=self.child_two,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

        out, _ = self._call_command("--family", self.family.slug)

        self.assertIn("Skipped 1 ambiguous pair(s)", out)
        self.assertFalse(
            Relationship.objects.filter(
                family=self.family,
                from_person=self.mother,
                to_person=self.child_two,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )

    def test_aggressive_mode_links_missing_parent_when_siblings_share_one(self):
        Relationship.objects.create(
            family=self.family,
            from_person=self.father,
            to_person=self.child_two,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

        out, _ = self._call_command("--family", self.family.slug, "--aggressive")

        self.assertIn("Creating", out)
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=self.mother,
                to_person=self.child_two,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )

    def test_aggressive_mode_skips_siblings_with_no_shared_parents(self):
        other_father = Person.objects.create(
            family=self.family,
            first_name="Other",
            last_name="Father",
            created_by=self.owner,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=other_father,
            to_person=self.child_two,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

        out, _ = self._call_command("--family", self.family.slug)

        self.assertIn("Skipped 1 ambiguous pair(s)", out)
