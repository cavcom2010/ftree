from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.families.models import Family
from apps.people.models import Person
from apps.relationships.models import Relationship
from apps.relationships.services import find_relationship_path

User = get_user_model()


class FindRelationshipPathTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester")
        self.family = Family.objects.create(name="Test Family", slug="test-family")

        self.alice = Person.objects.create(
            family=self.family, first_name="Alice", last_name="Smith",
            gender="female", birth_date=date(1950, 1, 1), created_by=self.user,
        )
        self.bob = Person.objects.create(
            family=self.family, first_name="Bob", last_name="Smith",
            gender="male", birth_date=date(1952, 1, 1), created_by=self.user,
        )
        self.charlie = Person.objects.create(
            family=self.family, first_name="Charlie", last_name="Smith",
            gender="male", birth_date=date(1980, 1, 1), created_by=self.user,
        )
        self.diana = Person.objects.create(
            family=self.family, first_name="Diana", last_name="Smith",
            gender="female", birth_date=date(2010, 1, 1), created_by=self.user,
        )
        self.eve = Person.objects.create(
            family=self.family, first_name="Eve", last_name="Outsider",
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
            from_person=self.bob,
            to_person=self.charlie,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.charlie,
            to_person=self.diana,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

    def test_path_between_parent_and_grandchild(self):
        path = find_relationship_path(self.alice, self.diana)
        self.assertIsNotNone(path)
        self.assertEqual(len(path), 3)
        self.assertEqual(path[0], self.alice)
        self.assertEqual(path[1], self.charlie)
        self.assertEqual(path[2], self.diana)

    def test_path_between_siblings_through_parent(self):
        path = find_relationship_path(self.alice, self.bob)
        self.assertIsNotNone(path)
        self.assertEqual(len(path), 3)
        self.assertIn(self.charlie, path)

    def test_path_same_person_returns_self(self):
        path = find_relationship_path(self.alice, self.alice)
        self.assertIsNotNone(path)
        self.assertEqual(len(path), 1)
        self.assertEqual(path[0], self.alice)

    def test_path_returns_none_for_disconnected_person(self):
        path = find_relationship_path(self.alice, self.eve)
        self.assertIsNone(path)

    def test_path_between_child_and_grandparent(self):
        path = find_relationship_path(self.diana, self.bob)
        self.assertIsNotNone(path)
        self.assertEqual(len(path), 3)
        self.assertEqual(path[0], self.diana)
        self.assertEqual(path[2], self.bob)
