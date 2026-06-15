from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.families.models import Family
from apps.people.models import Person, person_profile_photo_upload_path
from apps.people.services import (
    get_children,
    get_descendant_generation,
    get_generation_label,
    get_generation_rows,
)
from apps.relationships.models import Relationship

User = get_user_model()


class PersonFullNameTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester")
        self.family = Family.objects.create(name="Test Family", slug="test-family")

    def test_full_name_first_and_last(self):
        person = Person.objects.create(
            family=self.family,
            first_name="Alice",
            last_name="Smith",
            created_by=self.user,
        )
        self.assertEqual(person.full_name, "Alice Smith")

    def test_full_name_with_middle(self):
        person = Person.objects.create(
            family=self.family,
            first_name="Bob",
            middle_name="Lee",
            last_name="Jones",
            created_by=self.user,
        )
        self.assertEqual(person.full_name, "Bob Lee Jones")

    def test_full_name_without_middle(self):
        person = Person.objects.create(
            family=self.family,
            first_name="Charlie",
            last_name="Brown",
            created_by=self.user,
        )
        self.assertEqual(person.full_name, "Charlie Brown")


class PersonProfilePhotoPathTests(TestCase):
    def test_profile_photo_upload_path_is_clean_and_unique(self):
        first_path = person_profile_photo_upload_path(None, "Portrait.JPG")
        second_path = person_profile_photo_upload_path(None, "Portrait.JPG")

        self.assertTrue(first_path.startswith("people/profile-photos/"))
        self.assertTrue(first_path.endswith(".jpg"))
        self.assertNotEqual(first_path, second_path)


class RelationshipDirectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester")
        self.family = Family.objects.create(name="Test Family", slug="test-family")
        self.alice = Person.objects.create(
            family=self.family, first_name="Alice", last_name="Smith",
            gender="female", birth_date=date(1950, 1, 1), created_by=self.user,
        )
        self.charlie = Person.objects.create(
            family=self.family, first_name="Charlie", last_name="Smith",
            gender="male", birth_date=date(1980, 1, 1), created_by=self.user,
        )
        self.rel = Relationship.objects.create(
            family=self.family,
            from_person=self.alice,
            to_person=self.charlie,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

    def test_from_person_is_parent(self):
        self.assertEqual(self.rel.relationship_type, "parent_child")
        self.assertEqual(self.rel.from_person, self.alice)

    def test_to_person_is_child(self):
        self.assertEqual(self.rel.to_person, self.charlie)

    def test_parent_child_label(self):
        self.assertEqual(
            self.rel.get_relationship_type_display(),
            "Parent → Child",
        )


class GetChildrenTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester")
        self.family = Family.objects.create(name="Test Family", slug="test-family")
        self.alice = Person.objects.create(
            family=self.family, first_name="Alice", last_name="Smith",
            gender="female", created_by=self.user,
        )
        self.charlie = Person.objects.create(
            family=self.family, first_name="Charlie", last_name="Smith",
            gender="male", created_by=self.user,
        )
        self.diana = Person.objects.create(
            family=self.family, first_name="Diana", last_name="Smith",
            gender="female", created_by=self.user,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.alice,
            to_person=self.charlie,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.alice,
            to_person=self.diana,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

    def test_get_children_returns_correct_children(self):
        children = get_children(self.alice)
        self.assertEqual(children.count(), 2)
        names = {c.first_name for c in children}
        self.assertIn("Charlie", names)
        self.assertIn("Diana", names)

    def test_get_children_returns_empty_for_childless_person(self):
        children = get_children(self.charlie)
        self.assertEqual(children.count(), 0)


class GetDescendantGenerationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester")
        self.family = Family.objects.create(name="Test Family", slug="test-family")
        self.alice = Person.objects.create(
            family=self.family, first_name="Alice", last_name="Smith",
            gender="female", created_by=self.user,
        )
        self.charlie = Person.objects.create(
            family=self.family, first_name="Charlie", last_name="Smith",
            gender="male", created_by=self.user,
        )
        self.diana = Person.objects.create(
            family=self.family, first_name="Diana", last_name="Smith",
            gender="female", created_by=self.user,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.alice,
            to_person=self.charlie,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.alice,
            to_person=self.diana,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

    def test_descendant_generation_has_correct_children(self):
        gen = get_descendant_generation(self.alice)
        self.assertIsNotNone(gen)
        self.assertIsNone(gen["number"])
        self.assertEqual(gen["label"], "Children")
        self.assertEqual(len(gen["people"]), 2)
        names = {c.first_name for c in gen["people"]}
        self.assertIn("Charlie", names)
        self.assertIn("Diana", names)

    def test_descendant_generation_is_none_for_childless(self):
        gen = get_descendant_generation(self.charlie)
        self.assertIsNone(gen)

    def test_generation_label_is_founder_for_person_without_parents(self):
        self.assertEqual(get_generation_label(self.alice), "Founder")

    def test_generation_label_is_descendant_for_person_with_parent(self):
        self.assertEqual(get_generation_label(self.charlie), "Descendant")


class GetGenerationRowsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester")
        self.family = Family.objects.create(name="Test Family", slug="test-family")

    def make_person(self, first_name, last_name="Smith", birth_date=None):
        return Person.objects.create(
            family=self.family,
            first_name=first_name,
            last_name=last_name,
            birth_date=birth_date,
            created_by=self.user,
        )

    def add_parent_child(self, parent, child):
        return Relationship.objects.create(
            family=self.family,
            from_person=parent,
            to_person=child,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

    def add_legacy_parent_child_without_validation(self, parent, child):
        """Create deliberately corrupt legacy data for service-level safety tests.

        Normal application code must use Relationship.objects.create(), which now
        validates and rejects ancestry cycles. This helper bypasses model save()
        so get_generation_rows() can still prove it will not loop forever if old
        or manually imported bad data already exists in the database.
        """
        [relationship] = Relationship.objects.bulk_create([
            Relationship(
                family=self.family,
                from_person=parent,
                to_person=child,
                relationship_type=Relationship.Type.PARENT_CHILD,
            )
        ])
        return relationship

    def row_names(self, rows):
        return [[person.first_name for person in row["people"]] for row in rows]

    def test_simple_parent_child_tree(self):
        parent = self.make_person("Alice", birth_date=date(1950, 1, 1))
        child = self.make_person("Charlie", birth_date=date(1980, 1, 1))
        grandchild = self.make_person("Diana", birth_date=date(2010, 1, 1))
        self.add_parent_child(parent, child)
        self.add_parent_child(child, grandchild)

        rows = get_generation_rows(self.family)

        self.assertEqual(self.row_names(rows), [["Alice"], ["Charlie"], ["Diana"]])
        self.assertEqual([row["number"] for row in rows], [1, 2, 3])
        self.assertEqual(
            [row["label"] for row in rows],
            ["Founders", "Children", "Grandchildren"],
        )

    def test_multiple_roots_are_ordered_by_birth_date_then_name(self):
        younger_root = self.make_person("Zara", "Root", date(1960, 1, 1))
        self.make_person("Betty", "Root", date(1940, 1, 1))
        self.make_person("Adam", "Root", date(1940, 1, 1))
        child = self.make_person("Child", "Root", date(1980, 1, 1))
        self.add_parent_child(younger_root, child)

        rows = get_generation_rows(self.family)

        self.assertEqual(
            self.row_names(rows),
            [["Adam", "Betty", "Zara"], ["Child"]],
        )

    def test_child_with_two_parents_appears_only_once(self):
        parent_a = self.make_person("Alice", birth_date=date(1950, 1, 1))
        parent_b = self.make_person("Bob", birth_date=date(1951, 1, 1))
        child = self.make_person("Charlie", birth_date=date(1980, 1, 1))
        self.add_parent_child(parent_a, child)
        self.add_parent_child(parent_b, child)

        rows = get_generation_rows(self.family)

        self.assertEqual(self.row_names(rows), [["Alice", "Bob"], ["Charlie"]])
        self.assertEqual(sum(row.count("Charlie") for row in self.row_names(rows)), 1)

    def test_cycle_protection_does_not_repeat_people(self):
        root = self.make_person("Alice", birth_date=date(1950, 1, 1))
        child = self.make_person("Bob", birth_date=date(1980, 1, 1))
        grandchild = self.make_person("Cara", birth_date=date(2010, 1, 1))
        self.add_parent_child(root, child)
        self.add_parent_child(child, grandchild)
        self.add_legacy_parent_child_without_validation(grandchild, child)

        rows = get_generation_rows(self.family)

        self.assertEqual(self.row_names(rows), [["Alice"], ["Bob"], ["Cara"]])
        flattened_ids = [person.id for row in rows for person in row["people"]]
        self.assertEqual(len(flattened_ids), len(set(flattened_ids)))
