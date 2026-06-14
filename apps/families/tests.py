from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.families.models import Family, FamilyInvitation, FamilyMembership
from apps.families.services import (
    accept_invitation,
    create_invitation,
    create_relative,
    create_relative_invitation,
    create_relative_with_optional_invite,
    decline_invitation,
)
from apps.people.models import Person
from apps.relationships.models import Relationship

User = get_user_model()


class FamilyInvitationServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="secret",
        )
        self.invitee = User.objects.create_user(
            username="cousin",
            email="cousin@example.com",
            password="secret",
        )
        self.family = Family.objects.create(name="Primary Family", slug="primary", created_by=self.owner)
        self.anchor = Person.objects.create(
            family=self.family,
            first_name="David",
            last_name="Johnson",
            created_by=self.owner,
        )
        self.target = Person.objects.create(
            family=self.family,
            first_name="Laura",
            last_name="Johnson",
            created_by=self.owner,
        )
        FamilyMembership.objects.create(
            family=self.family,
            user=self.owner,
            person=self.anchor,
            role=FamilyMembership.Role.OWNER,
        )

    def test_create_invitation_does_not_create_membership_until_acceptance(self):
        invitation = create_invitation(
            family=self.family,
            inviter=self.owner,
            person=self.target,
            invitee_identifier="cousin",
        )

        self.assertEqual(invitation.status, FamilyInvitation.Status.PENDING)
        self.assertEqual(invitation.invitee_user, self.invitee)
        self.assertFalse(FamilyMembership.objects.filter(user=self.invitee, family=self.family).exists())

    def test_accept_invitation_links_user_to_person(self):
        invitation = create_invitation(
            family=self.family,
            inviter=self.owner,
            person=self.target,
            invitee_identifier="cousin@example.com",
        )

        membership = accept_invitation(invitation, self.invitee)
        invitation.refresh_from_db()

        self.assertEqual(invitation.status, FamilyInvitation.Status.ACCEPTED)
        self.assertEqual(membership.person, self.target)
        self.assertEqual(membership.family, self.family)

    def test_decline_invitation_does_not_create_membership(self):
        invitation = create_invitation(
            family=self.family,
            inviter=self.owner,
            person=self.target,
            invitee_identifier="cousin@example.com",
        )

        decline_invitation(invitation, self.invitee)
        invitation.refresh_from_db()

        self.assertEqual(invitation.status, FamilyInvitation.Status.DECLINED)
        self.assertFalse(FamilyMembership.objects.filter(user=self.invitee, family=self.family).exists())

    def test_duplicate_pending_invitation_for_person_is_blocked(self):
        create_invitation(
            family=self.family,
            inviter=self.owner,
            person=self.target,
            invitee_identifier="cousin@example.com",
        )

        with self.assertRaisesMessage(ValidationError, "already has a pending invitation"):
            create_invitation(
                family=self.family,
                inviter=self.owner,
                person=self.target,
                invitee_identifier="other@example.com",
            )

    def test_viewer_cannot_invite(self):
        viewer = User.objects.create_user(username="viewer", email="viewer@example.com", password="secret")
        FamilyMembership.objects.create(
            family=self.family,
            user=viewer,
            role=FamilyMembership.Role.VIEWER,
        )

        with self.assertRaises(PermissionDenied):
            create_invitation(
                family=self.family,
                inviter=viewer,
                person=self.target,
                invitee_identifier="cousin@example.com",
            )

    def test_create_relative_invitation_adds_pending_person_and_relationship(self):
        invitation = create_relative_invitation(
            family=self.family,
            inviter=self.owner,
            anchor_person=self.anchor,
            relation_type="child",
            person_data={
                "first_name": "Olivia",
                "last_name": "Johnson",
                "gender": Person.Gender.FEMALE,
                "birth_date": None,
            },
            invitee_identifier="olivia@example.com",
        )

        self.assertEqual(invitation.status, FamilyInvitation.Status.PENDING)
        self.assertEqual(invitation.person.first_name, "Olivia")
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=self.anchor,
                to_person=invitation.person,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )

    def test_create_relative_without_invite_adds_unclaimed_person_and_relationship(self):
        person, relationship_type = create_relative(
            family=self.family,
            inviter=self.owner,
            anchor_person=self.anchor,
            relation_type="child",
            person_data={
                "first_name": "Mia",
                "last_name": "Johnson",
                "gender": Person.Gender.FEMALE,
                "birth_date": None,
            },
        )

        self.assertEqual(person.first_name, "Mia")
        self.assertEqual(relationship_type, Relationship.Type.PARENT_CHILD)
        self.assertFalse(FamilyInvitation.objects.filter(person=person).exists())
        self.assertFalse(FamilyMembership.objects.filter(person=person).exists())
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=self.anchor,
                to_person=person,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )

    def test_create_relative_parent_uses_parent_to_child_direction(self):
        person, _ = create_relative(
            family=self.family,
            inviter=self.owner,
            anchor_person=self.anchor,
            relation_type="parent",
            person_data={
                "first_name": "Ellen",
                "last_name": "Johnson",
                "gender": Person.Gender.FEMALE,
                "birth_date": None,
            },
        )

        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=person,
                to_person=self.anchor,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )

    def test_create_relative_partner_uses_spouse_relationship(self):
        person, relationship_type = create_relative(
            family=self.family,
            inviter=self.owner,
            anchor_person=self.anchor,
            relation_type="partner",
            person_data={
                "first_name": "Sam",
                "last_name": "Johnson",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": None,
            },
        )

        self.assertEqual(relationship_type, Relationship.Type.SPOUSE)
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=self.anchor,
                to_person=person,
                relationship_type=Relationship.Type.SPOUSE,
            ).exists()
        )

    def test_create_relative_with_optional_invite_can_add_without_invitation(self):
        person, invitation = create_relative_with_optional_invite(
            family=self.family,
            inviter=self.owner,
            anchor_person=self.anchor,
            relation_type="child",
            person_data={
                "first_name": "Blank",
                "last_name": "Invite",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": None,
            },
            invitee_identifier="",
        )

        self.assertIsNone(invitation)
        self.assertFalse(FamilyInvitation.objects.filter(person=person).exists())

    def test_create_relative_with_optional_invite_rolls_back_invalid_invite(self):
        with self.assertRaisesMessage(ValidationError, "Enter an email address"):
            create_relative_with_optional_invite(
                family=self.family,
                inviter=self.owner,
                anchor_person=self.anchor,
                relation_type="child",
                person_data={
                    "first_name": "Rollback",
                    "last_name": "Invite",
                    "gender": Person.Gender.UNKNOWN,
                    "birth_date": None,
                },
                invitee_identifier="not-a-user",
            )

        self.assertFalse(Person.objects.filter(first_name="Rollback", family=self.family).exists())

    def test_viewer_cannot_create_relative(self):
        viewer = User.objects.create_user(username="limited", email="limited@example.com", password="secret")
        FamilyMembership.objects.create(
            family=self.family,
            user=viewer,
            role=FamilyMembership.Role.VIEWER,
        )

        with self.assertRaises(PermissionDenied):
            create_relative(
                family=self.family,
                inviter=viewer,
                anchor_person=self.anchor,
                relation_type="child",
                person_data={
                    "first_name": "Blocked",
                    "last_name": "Person",
                    "gender": Person.Gender.UNKNOWN,
                    "birth_date": None,
                },
            )


class FamilyInvitationViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", email="owner@example.com", password="secret")
        self.invitee = User.objects.create_user(username="invitee", email="invitee@example.com", password="secret")
        self.family = Family.objects.create(name="View Family", slug="view-family", created_by=self.owner)
        self.anchor = Person.objects.create(family=self.family, first_name="Owner", last_name="Person", created_by=self.owner)
        self.target = Person.objects.create(family=self.family, first_name="Target", last_name="Person", created_by=self.owner)
        FamilyMembership.objects.create(
            family=self.family,
            user=self.owner,
            person=self.anchor,
            role=FamilyMembership.Role.OWNER,
        )

    def test_tree_invite_person_endpoint_creates_pending_invitation(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            f"/tree/people/{self.target.id}/invite/",
            {
                "invitee": "invitee@example.com",
                "role": FamilyMembership.Role.MEMBER,
                "message": "Join us",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invite sent")
        self.assertTrue(FamilyInvitation.objects.filter(person=self.target, invitee_user=self.invitee).exists())

    def test_tree_invite_relative_endpoint_creates_pending_person(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            f"/tree/people/{self.anchor.id}/invite-relative/child/",
            {
                "first_name": "Young",
                "last_name": "Person",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": "",
                "invitee": "young@example.com",
                "role": FamilyMembership.Role.MEMBER,
                "message": "Join this branch",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Relative added")
        invitation = FamilyInvitation.objects.get(invitee_email="young@example.com")
        self.assertEqual(invitation.person.first_name, "Young")
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=self.anchor,
                to_person=invitation.person,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )

    def test_tree_invite_relative_endpoint_can_add_without_invitation(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            f"/tree/people/{self.anchor.id}/invite-relative/partner/",
            {
                "first_name": "No",
                "last_name": "Invite",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": "",
                "invitee": "",
                "role": FamilyMembership.Role.MEMBER,
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Relative added")
        person = Person.objects.get(first_name="No", last_name="Invite")
        self.assertFalse(FamilyInvitation.objects.filter(person=person).exists())
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=self.anchor,
                to_person=person,
                relationship_type=Relationship.Type.SPOUSE,
            ).exists()
        )

    def test_tree_invite_relative_endpoint_shows_errors_without_creating_person(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            f"/tree/people/{self.anchor.id}/invite-relative/child/",
            {
                "first_name": "Bad",
                "last_name": "Invite",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": "",
                "invitee": "unknown-username",
                "role": FamilyMembership.Role.MEMBER,
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter an email address")
        self.assertFalse(Person.objects.filter(first_name="Bad", family=self.family).exists())

    def test_accept_invitation_view_connects_user(self):
        invitation = create_invitation(
            family=self.family,
            inviter=self.owner,
            person=self.target,
            invitee_identifier="invitee@example.com",
        )
        self.client.force_login(self.invitee)

        response = self.client.post(f"/invitations/{invitation.token}/accept/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(FamilyMembership.objects.filter(user=self.invitee, person=self.target).exists())
