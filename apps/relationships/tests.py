from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.families.models import Family
from apps.people.models import Person
from apps.relationships.models import Relationship


class RelationshipValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="demo12345")
        self.family = Family.objects.create(name="Validation Family", slug="validation", created_by=self.user)

    def make_person(self, first_name):
        return Person.objects.create(
            family=self.family,
            first_name=first_name,
            last_name="Test",
            created_by=self.user,
        )

    def test_validation_rejects_same_source_and_target(self):
        person = self.make_person("Alex")

        with self.assertRaises(ValidationError):
            Relationship.objects.create(
                family=self.family,
                from_person=person,
                to_person=person,
                relationship_type=Relationship.Type.PARENT_CHILD,
            )

    def test_validation_rejects_reverse_symmetric_duplicate(self):
        first = self.make_person("First")
        second = self.make_person("Second")
        Relationship.objects.create(
            family=self.family,
            from_person=first,
            to_person=second,
            relationship_type=Relationship.Type.SPOUSE,
        )

        with self.assertRaises(ValidationError):
            Relationship.objects.create(
                family=self.family,
                from_person=second,
                to_person=first,
                relationship_type=Relationship.Type.SPOUSE,
            )
