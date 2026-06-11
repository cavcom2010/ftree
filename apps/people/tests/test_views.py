from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.families.models import Family, FamilyMembership
from apps.people.models import Person

User = get_user_model()


class PersonViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="secret")
        self.client.force_login(self.user)

    def test_person_create_returns_404_when_no_family_exists(self):
        response = self.client.post(
            "/people/create/",
            {
                "first_name": "Alice",
                "last_name": "Smith",
                "gender": Person.Gender.UNKNOWN,
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Person.objects.exists())

    def test_person_drawer_is_scoped_to_current_family(self):
        primary_family = Family.objects.create(name="Primary Family", slug="primary")
        FamilyMembership.objects.create(family=primary_family, user=self.user)
        other_family = Family.objects.create(name="Other Family", slug="other")
        other_person = Person.objects.create(
            family=other_family,
            first_name="Hidden",
            last_name="Person",
            created_by=self.user,
        )

        response = self.client.get(f"/people/{other_person.id}/drawer/")

        self.assertEqual(response.status_code, 404)
