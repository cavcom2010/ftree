from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.families.models import Family, FamilyMembership
from apps.people.models import Person
from apps.relationships.models import Relationship

User = get_user_model()


class AddRelativeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="secret")
        self.client.force_login(self.user)

    def test_add_relative_rejects_person_outside_current_family(self):
        primary_family = Family.objects.create(name="Primary Family", slug="primary")
        FamilyMembership.objects.create(family=primary_family, user=self.user)
        other_family = Family.objects.create(name="Other Family", slug="other")
        other_person = Person.objects.create(
            family=other_family,
            first_name="Hidden",
            last_name="Person",
            created_by=self.user,
        )

        response = self.client.post(
            f"/people/{other_person.id}/add-relative/child/",
            {
                "first_name": "New",
                "last_name": "Child",
                "gender": Person.Gender.UNKNOWN,
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Person.objects.count(), 1)
        self.assertFalse(Relationship.objects.exists())
