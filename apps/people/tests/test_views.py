from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.families.models import Family, FamilyMembership
from apps.people.models import Person
from apps.relationships.models import Relationship

User = get_user_model()


class PersonViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="secret")
        self.client.force_login(self.user)

    def test_person_create_route_redirects_to_tree_without_creating_orphans(self):
        response = self.client.get("/people/create/")

        self.assertContains(response, "Add Person")
        self.assertFalse(Person.objects.exists())

        post_response = self.client.post(
            "/people/create/",
            {
                "first_name": "Alice",
                "last_name": "Smith",
                "gender": Person.Gender.UNKNOWN,
            },
        )

        self.assertEqual(post_response.status_code, 404)
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

    def test_person_drawer_exposes_add_sibling_for_family_owner(self):
        family = Family.objects.create(name="Owner Family", slug="owner-family")
        anchor = Person.objects.create(
            family=family,
            first_name="Owner",
            last_name="Person",
            created_by=self.user,
        )
        father = Person.objects.create(
            family=family,
            first_name="Father",
            last_name="Person",
            created_by=self.user,
        )
        FamilyMembership.objects.create(
            family=family,
            user=self.user,
            person=anchor,
            role=FamilyMembership.Role.OWNER,
        )
        Relationship.objects.create(
            family=family,
            from_person=father,
            to_person=anchor,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

        response = self.client.get(reverse("person_drawer", args=[father.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sibling")
        self.assertContains(response, f'/tree/people/{father.id}/invite-relative/sibling/')
        self.assertContains(response, "Edit Name")

    def test_current_user_can_edit_their_tree_name(self):
        family = Family.objects.create(name="Test Family", slug="test-family")
        person = Person.objects.create(
            family=family,
            first_name="Auto",
            last_name="Generated",
            created_by=self.user,
        )
        FamilyMembership.objects.create(
            family=family,
            user=self.user,
            person=person,
            role=FamilyMembership.Role.OWNER,
        )

        response = self.client.post(
            reverse("person_edit_name", args=[person.id]),
            {
                "first_name": "Calvin",
                "middle_name": "",
                "last_name": "Mazhindu",
                "maiden_name": "",
            },
        )

        self.assertRedirects(response, reverse("tree"))
        person.refresh_from_db()
        self.assertEqual(person.first_name, "Calvin")
        self.assertEqual(person.last_name, "Mazhindu")

    def test_person_name_edit_form_is_scoped_to_current_family(self):
        primary_family = Family.objects.create(name="Primary Family", slug="primary")
        FamilyMembership.objects.create(family=primary_family, user=self.user)
        other_family = Family.objects.create(name="Other Family", slug="other")
        other_person = Person.objects.create(
            family=other_family,
            first_name="Hidden",
            last_name="Person",
            created_by=self.user,
        )

        response = self.client.get(reverse("person_edit_name", args=[other_person.id]))

        self.assertEqual(response.status_code, 404)

    def test_unclaimed_person_can_be_edited_by_family_owner(self):
        family = Family.objects.create(name="Owner Family", slug="owner-family")
        owner_person = Person.objects.create(
            family=family,
            first_name="Owner",
            last_name="Person",
            created_by=self.user,
        )
        editable_person = Person.objects.create(
            family=family,
            first_name="Wrong",
            last_name="Name",
            created_by=self.user,
        )
        FamilyMembership.objects.create(
            family=family,
            user=self.user,
            person=owner_person,
            role=FamilyMembership.Role.OWNER,
        )

        response = self.client.post(
            reverse("person_edit_name", args=[editable_person.id]),
            {
                "first_name": "Right",
                "middle_name": "",
                "last_name": "Name",
                "maiden_name": "",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        editable_person.refresh_from_db()
        self.assertEqual(editable_person.first_name, "Right")
        self.assertContains(response, "Name updated")

    def test_person_descendants_partial_renders_children(self):
        family = Family.objects.create(name="Descendant Family", slug="descendant-family")
        parent = Person.objects.create(
            family=family,
            first_name="Parent",
            last_name="Person",
            created_by=self.user,
        )
        child = Person.objects.create(
            family=family,
            first_name="Child",
            last_name="Person",
            created_by=self.user,
        )
        FamilyMembership.objects.create(
            family=family,
            user=self.user,
            person=parent,
            role=FamilyMembership.Role.OWNER,
        )
        Relationship.objects.create(
            family=family,
            from_person=parent,
            to_person=child,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

        response = self.client.get(reverse("person_descendants", args=[parent.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Children")
        self.assertContains(response, "Child")
