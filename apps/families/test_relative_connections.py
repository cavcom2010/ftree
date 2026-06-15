from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.families.models import Family, FamilyMembership
from apps.families.services import create_relative
from apps.people.models import Person
from apps.relationships.models import Relationship

User = get_user_model()


class ExistingRelativeConnectionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner-connections",
            email="owner-connections@example.com",
            password="secret",
        )
        self.family = Family.objects.create(
            name="Connection Family",
            slug="connection-family",
            created_by=self.owner,
        )
        self.anchor = Person.objects.create(
            family=self.family,
            first_name="Calvin",
            last_name="Mazhindu",
            created_by=self.owner,
        )
        FamilyMembership.objects.create(
            family=self.family,
            user=self.owner,
            person=self.anchor,
            role=FamilyMembership.Role.OWNER,
        )

    def test_adding_partner_can_connect_existing_shared_children(self):
        child = Person.objects.create(
            family=self.family,
            first_name="Shared",
            last_name="Child",
            created_by=self.owner,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.anchor,
            to_person=child,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

        partner, relationship_type = create_relative(
            family=self.family,
            inviter=self.owner,
            anchor_person=self.anchor,
            relation_type="partner",
            person_data={
                "first_name": "Barbara",
                "last_name": "Mazhindu",
                "gender": Person.Gender.FEMALE,
                "birth_date": None,
            },
            partner_relationship_type=Relationship.Type.SPOUSE,
            partner_shared_children=[child],
        )

        self.assertEqual(relationship_type, Relationship.Type.SPOUSE)
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=self.anchor,
                to_person=partner,
                relationship_type=Relationship.Type.SPOUSE,
            ).exists()
        )
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=partner,
                to_person=child,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )

    def test_adding_parent_can_connect_existing_siblings_as_that_parents_children(self):
        sibling = Person.objects.create(
            family=self.family,
            first_name="Known",
            last_name="Sibling",
            created_by=self.owner,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.anchor,
            to_person=sibling,
            relationship_type=Relationship.Type.SIBLING,
        )

        parent, relationship_type = create_relative(
            family=self.family,
            inviter=self.owner,
            anchor_person=self.anchor,
            relation_type="parent",
            person_data={
                "first_name": "New",
                "last_name": "Parent",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": None,
            },
            parent_relationship_type=Relationship.Type.PARENT_CHILD,
            parent_shared_children=[sibling],
        )

        self.assertEqual(relationship_type, Relationship.Type.PARENT_CHILD)
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=parent,
                to_person=self.anchor,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=parent,
                to_person=sibling,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )

    def test_adding_partner_rejects_selected_child_who_is_not_anchor_child(self):
        not_child = Person.objects.create(
            family=self.family,
            first_name="Not",
            last_name="Child",
            created_by=self.owner,
        )

        with self.assertRaisesMessage(ValidationError, "Shared children"):
            create_relative(
                family=self.family,
                inviter=self.owner,
                anchor_person=self.anchor,
                relation_type="partner",
                person_data={
                    "first_name": "Invalid",
                    "last_name": "Partner",
                    "gender": Person.Gender.UNKNOWN,
                    "birth_date": None,
                },
                partner_shared_children=[not_child],
            )

    def test_invite_relative_sheet_shows_shared_connection_choices(self):
        child = Person.objects.create(
            family=self.family,
            first_name="Existing",
            last_name="Child",
            created_by=self.owner,
        )
        sibling = Person.objects.create(
            family=self.family,
            first_name="Existing",
            last_name="Sibling",
            created_by=self.owner,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.anchor,
            to_person=child,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.anchor,
            to_person=sibling,
            relationship_type=Relationship.Type.SIBLING,
        )
        self.client.force_login(self.owner)

        partner_response = self.client.get(f"/tree/people/{self.anchor.id}/invite-relative/partner/")
        parent_response = self.client.get(f"/tree/people/{self.anchor.id}/invite-relative/parent/")

        self.assertContains(partner_response, "Children you share with this partner")
        self.assertContains(partner_response, "Existing Child")
        self.assertContains(parent_response, "Existing siblings who are also this parent&#x27;s children")
        self.assertContains(parent_response, "Existing Sibling")
