from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.families.models import Family
from apps.people.models import Person
from apps.people.services import get_children, get_descendant_generation
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
            middle_name="James",
            last_name="Jones",
            created_by=self.user,
        )
        self.assertEqual(person.full_name, "Bob James Jones")

    def test_full_name_without_middle(self):
        person = Person.objects.create(
            family=self.family,
            first_name="Charlie",
            last_name="Brown",
            created_by=self.user,
        )
        self.assertEqual(person.full_name, "Charlie Brown")


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
        self.assertEqual(len(gen["people"]), 2)
        names = {c.first_name for c in gen["people"]}
        self.assertIn("Charlie", names)
        self.assertIn("Diana", names)

    def test_descendant_generation_is_none_for_childless(self):
        gen = get_descendant_generation(self.charlie)
        self.assertIsNone(gen)
