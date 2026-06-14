from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.families.models import Family, FamilyInvitation, FamilyMembership
from apps.families.services import (
    accept_invitation,
    create_invitation,
    create_relative_invitation,
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
        self.assertContains(response, "Invite sent")
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
