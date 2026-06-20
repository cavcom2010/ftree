import json
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.core.tree_context import build_tree_context
from apps.families.forms import InviteRelativeForm
from apps.families.models import Family, FamilyInvitation, FamilyMembership
from apps.families.services import (
    accept_invitation,
    create_invitation,
    create_relative,
    create_relative_invitation,
    create_relative_with_optional_invite,
    decline_invitation,
)
from apps.memories.models import Memory
from apps.people.models import Person
from apps.relationships.models import Relationship
from apps.social.models import Activity
from apps.stories.models import Story

User = get_user_model()


class PublicDiscoveryPrivacyTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="public-owner",
            email="public-owner@example.com",
            password="secret",
        )
        self.viewer = User.objects.create_user(
            username="public-viewer",
            email="public-viewer@example.com",
            password="secret",
        )
        self.family = Family.objects.create(
            name="Safe Discovery Family",
            slug="safe-discovery",
            created_by=self.owner,
            visibility=Family.Visibility.PUBLIC_ANCESTORS,
            description="Secret internal owner notes",
            public_summary="",
            main_surnames=["SafeSurname"],
            maiden_surnames=["HiddenMaiden"],
            allow_public_surname_search=True,
        )
        self.public_ancestor = Person.objects.create(
            family=self.family,
            first_name="Ada",
            last_name="SafeSurname",
            birth_date=date(1910, 1, 1),
            death_date=date(1980, 1, 1),
            is_living=False,
            visibility=Person.Visibility.PUBLIC_IF_DECEASED,
            created_by=self.owner,
        )
        self.private_living = Person.objects.create(
            family=self.family,
            first_name="Living",
            last_name="SecretSurname",
            maiden_name="HiddenMaiden",
            birth_date=date(2000, 2, 3),
            birth_place="Secret Birthplace",
            current_place="Secret Current Place",
            biography="Private biography text",
            is_living=True,
            is_private=True,
            created_by=self.owner,
        )

    def test_public_gallery_uses_only_public_safe_card_fields(self):
        response = self.client.get("/tree/?q=SafeSurname")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Safe Discovery Family")
        self.assertContains(response, "SafeSurname")
        self.assertNotContains(response, "Secret internal owner notes")
        self.assertNotContains(response, "HiddenMaiden")
        self.assertNotContains(response, "SecretSurname")

    def test_public_gallery_does_not_match_private_maiden_or_internal_description(self):
        maiden_response = self.client.get("/tree/?q=HiddenMaiden")
        description_response = self.client.get("/tree/?q=internal+owner")

        self.assertNotContains(maiden_response, "Safe Discovery Family")
        self.assertNotContains(description_response, "Safe Discovery Family")

    def test_public_surname_page_uses_explicit_public_surnames_only(self):
        public_response = self.client.get("/surnames/SafeSurname/")
        private_response = self.client.get("/surnames/SecretSurname/")

        self.assertContains(public_response, "Safe Discovery Family")
        self.assertNotContains(private_response, "Safe Discovery Family")

    def test_public_tree_redacts_living_private_people(self):
        response = self.client.get("/tree/public/safe-discovery/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ada SafeSurname")
        self.assertContains(response, "Private living person")
        self.assertNotContains(response, "Living SecretSurname")
        self.assertNotContains(response, "Secret Birthplace")
        self.assertNotContains(response, "Secret Current Place")
        self.assertNotContains(response, "Private biography text")

    def test_start_or_find_tree_does_not_suggest_from_private_living_profile(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            "/tree/start/",
            {
                "first_name": "Living",
                "middle_name": "",
                "last_name": "SecretSurname",
                "maiden_name": "HiddenMaiden",
                "birth_date": "2000-02-03",
                "parent_clue": "",
                "grandparent_clue": "",
                "region_clue": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Safe Discovery Family")


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

    def test_create_relative_can_add_another_partner(self):
        first_partner = Person.objects.create(
            family=self.family,
            first_name="First",
            last_name="Partner",
            created_by=self.owner,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.anchor,
            to_person=first_partner,
            relationship_type=Relationship.Type.SPOUSE,
        )

        second_partner, relationship_type = create_relative(
            family=self.family,
            inviter=self.owner,
            anchor_person=self.anchor,
            relation_type="partner",
            person_data={
                "first_name": "Second",
                "last_name": "Partner",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": None,
            },
            partner_relationship_type=Relationship.Type.PARTNER,
        )

        self.assertEqual(relationship_type, Relationship.Type.PARTNER)
        self.assertEqual(
            Relationship.objects.filter(
                family=self.family,
                from_person=self.anchor,
                relationship_type__in=[Relationship.Type.SPOUSE, Relationship.Type.PARTNER],
            ).count(),
            2,
        )
        self.assertTrue(Relationship.objects.filter(to_person=second_partner).exists())

    def test_create_partner_does_not_automatically_parent_existing_children(self):
        child = Person.objects.create(
            family=self.family,
            first_name="Existing",
            last_name="Child",
            created_by=self.owner,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.anchor,
            to_person=child,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

        partner, _ = create_relative(
            family=self.family,
            inviter=self.owner,
            anchor_person=self.anchor,
            relation_type="partner",
            person_data={
                "first_name": "Careful",
                "last_name": "Partner",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": None,
            },
        )

        self.assertFalse(
            Relationship.objects.filter(
                family=self.family,
                from_person=partner,
                to_person=child,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )

    def test_create_child_can_link_other_known_parent(self):
        partner = Person.objects.create(
            family=self.family,
            first_name="Known",
            last_name="Partner",
            created_by=self.owner,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.anchor,
            to_person=partner,
            relationship_type=Relationship.Type.SPOUSE,
        )

        child, _ = create_relative(
            family=self.family,
            inviter=self.owner,
            anchor_person=self.anchor,
            relation_type="child",
            person_data={
                "first_name": "Shared",
                "last_name": "Child",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": None,
            },
            other_parent=partner,
        )

        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=self.anchor,
                to_person=child,
                relationship_type=Relationship.Type.PARENT_CHILD,
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

    def test_create_child_rejects_other_parent_that_is_not_partner(self):
        not_partner = Person.objects.create(
            family=self.family,
            first_name="Not",
            last_name="Partner",
            created_by=self.owner,
        )

        with self.assertRaisesMessage(ValidationError, "known partner"):
            create_relative(
                family=self.family,
                inviter=self.owner,
                anchor_person=self.anchor,
                relation_type="child",
                person_data={
                    "first_name": "Bad",
                    "last_name": "Child",
                    "gender": Person.Gender.UNKNOWN,
                    "birth_date": None,
                },
                other_parent=not_partner,
            )

    def test_create_sibling_can_link_shared_parents(self):
        parent_one = Person.objects.create(
            family=self.family,
            first_name="Parent",
            last_name="One",
            created_by=self.owner,
        )
        parent_two = Person.objects.create(
            family=self.family,
            first_name="Parent",
            last_name="Two",
            created_by=self.owner,
        )
        for parent in [parent_one, parent_two]:
            Relationship.objects.create(
                family=self.family,
                from_person=parent,
                to_person=self.anchor,
                relationship_type=Relationship.Type.PARENT_CHILD,
            )

        sibling, relationship_type = create_relative(
            family=self.family,
            inviter=self.owner,
            anchor_person=self.anchor,
            relation_type="sibling",
            person_data={
                "first_name": "Shared",
                "last_name": "Sibling",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": None,
            },
            shared_parents=[parent_one, parent_two],
        )

        self.assertEqual(relationship_type, Relationship.Type.SIBLING)
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=self.anchor,
                to_person=sibling,
                relationship_type=Relationship.Type.SIBLING,
            ).exists()
        )
        self.assertEqual(
            Relationship.objects.filter(
                family=self.family,
                to_person=sibling,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).count(),
            2,
        )

    def test_create_sibling_rejects_unshared_parent(self):
        unrelated_parent = Person.objects.create(
            family=self.family,
            first_name="Unrelated",
            last_name="Parent",
            created_by=self.owner,
        )

        with self.assertRaisesMessage(ValidationError, "Shared parents"):
            create_relative(
                family=self.family,
                inviter=self.owner,
                anchor_person=self.anchor,
                relation_type="sibling",
                person_data={
                    "first_name": "Bad",
                    "last_name": "Sibling",
                    "gender": Person.Gender.UNKNOWN,
                    "birth_date": None,
                },
                shared_parents=[unrelated_parent],
            )

    def test_create_parent_supports_realistic_parent_types(self):
        for relationship_type in [
            Relationship.Type.ADOPTIVE_PARENT,
            Relationship.Type.STEP_PARENT,
            Relationship.Type.GUARDIAN,
        ]:
            with self.subTest(relationship_type=relationship_type):
                parent, created_type = create_relative(
                    family=self.family,
                    inviter=self.owner,
                    anchor_person=self.anchor,
                    relation_type="parent",
                    person_data={
                        "first_name": relationship_type.replace("_", "").title(),
                        "last_name": "Parent",
                        "gender": Person.Gender.UNKNOWN,
                        "birth_date": None,
                    },
                    parent_relationship_type=relationship_type,
                )

                self.assertEqual(created_type, relationship_type)
                self.assertTrue(
                    Relationship.objects.filter(
                        family=self.family,
                        from_person=parent,
                        to_person=self.anchor,
                        relationship_type=relationship_type,
                    ).exists()
                )

    def test_tree_context_groups_realistic_relationship_types(self):
        step_parent, _ = create_relative(
            family=self.family,
            inviter=self.owner,
            anchor_person=self.anchor,
            relation_type="parent",
            person_data={
                "first_name": "Step",
                "last_name": "Parent",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": None,
            },
            parent_relationship_type=Relationship.Type.STEP_PARENT,
        )
        partner, _ = create_relative(
            family=self.family,
            inviter=self.owner,
            anchor_person=self.anchor,
            relation_type="partner",
            person_data={
                "first_name": "Real",
                "last_name": "Partner",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": None,
            },
            partner_relationship_type=Relationship.Type.PARTNER,
        )

        context = build_tree_context(self.owner)
        anchor_card = context["tree_anchor"]

        self.assertIn(step_parent.full_name, [person["full_name"] for person in anchor_card["parents"]])
        self.assertIn(partner.full_name, [person["full_name"] for person in anchor_card["partners"]])

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

    def _tree_person_data(self, response, person):
        tree_data = json.loads(response.context["tree_json"])
        return next(item for item in tree_data["people"] if item["id"] == str(person.id))

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

    def test_tree_create_drawer_exposes_wired_actions(self):
        self.client.force_login(self.owner)

        response = self.client.get("/tree/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-tree-choose-person")
        self.assertContains(response, "data-tree-open-root-detail")
        self.assertContains(response, 'data-tree-sheet-panel="invite-status"')
        self.assertContains(response, 'data-tree-sheet-panel="connected-users"')
        self.assertNotContains(response, "Pending invites show on person cards")
        self.assertNotContains(response, "Accepted invitations connect users")

    def test_tree_create_drawer_lists_pending_invites_and_connections(self):
        create_invitation(
            family=self.family,
            inviter=self.owner,
            person=self.target,
            invitee_identifier="invitee@example.com",
        )
        self.client.force_login(self.owner)

        response = self.client.get("/tree/")

        self.assertContains(response, "Pending invite status")
        self.assertContains(response, "Target Person")
        self.assertContains(response, "invitee")
        self.assertContains(response, "Connected users")
        self.assertContains(response, "Owner Person")
        self.assertContains(response, "owner")

    def test_tree_json_separates_edit_from_add_relative_permission(self):
        viewer = User.objects.create_user(username="viewer", email="viewer@example.com", password="secret")
        FamilyMembership.objects.create(
            family=self.family,
            user=viewer,
            person=self.target,
            role=FamilyMembership.Role.VIEWER,
        )
        self.client.force_login(viewer)

        response = self.client.get("/tree/")
        target_data = self._tree_person_data(response, self.target)

        self.assertTrue(target_data["can_edit"])
        self.assertFalse(target_data["can_add_relative"])
        self.assertFalse(target_data["can_invite"])

    def test_tree_json_hides_invite_when_person_has_pending_invitation(self):
        create_invitation(
            family=self.family,
            inviter=self.owner,
            person=self.target,
            invitee_identifier="invitee@example.com",
        )
        self.client.force_login(self.owner)

        response = self.client.get("/tree/")
        target_data = self._tree_person_data(response, self.target)

        self.assertTrue(target_data["can_add_relative"])
        self.assertFalse(target_data["can_invite"])

    def test_tree_json_marks_deceased_person_and_hides_invite(self):
        self.target.is_living = False
        self.target.death_date = date(2009, 3, 12)
        self.target.save(update_fields=["is_living", "death_date"])
        self.client.force_login(self.owner)

        response = self.client.get("/tree/")
        target_data = self._tree_person_data(response, self.target)

        self.assertFalse(target_data["is_living"])
        self.assertEqual(target_data["death_date"], "12 Mar 2009")
        self.assertEqual(target_data["life_status"], "Died 12 Mar 2009")
        self.assertFalse(target_data["can_invite"])

    def test_tree_json_allows_add_relative_for_inviting_member(self):
        self.client.force_login(self.owner)

        response = self.client.get("/tree/")
        anchor_data = self._tree_person_data(response, self.anchor)

        self.assertTrue(anchor_data["can_add_relative"])
        self.assertFalse(anchor_data["can_invite"])

    def test_tree_json_hides_set_anchor_for_linked_account(self):
        self.client.force_login(self.owner)

        response = self.client.get("/tree/")
        target_data = self._tree_person_data(response, self.target)

        self.assertFalse(target_data["can_set_anchor"])

    def test_set_tree_anchor_does_not_reassign_linked_account(self):
        self.client.force_login(self.owner)

        response = self.client.post(f"/tree/people/{self.target.id}/set-anchor/")

        self.assertEqual(response.status_code, 302)
        membership = FamilyMembership.objects.get(family=self.family, user=self.owner)
        self.assertEqual(membership.person, self.anchor)

    def test_set_tree_anchor_allows_unlinked_membership_to_claim_person(self):
        viewer = User.objects.create_user(username="viewer", email="viewer@example.com", password="secret")
        FamilyMembership.objects.create(
            family=self.family,
            user=viewer,
            role=FamilyMembership.Role.VIEWER,
        )
        self.client.force_login(viewer)

        response = self.client.post(f"/tree/people/{self.target.id}/set-anchor/")

        self.assertEqual(response.status_code, 302)
        membership = FamilyMembership.objects.get(family=self.family, user=viewer)
        self.assertEqual(membership.person, self.target)

    def test_set_tree_anchor_blocks_claimed_person(self):
        viewer = User.objects.create_user(username="viewer", email="viewer@example.com", password="secret")
        FamilyMembership.objects.create(
            family=self.family,
            user=viewer,
            role=FamilyMembership.Role.VIEWER,
        )
        self.client.force_login(viewer)

        response = self.client.post(f"/tree/people/{self.anchor.id}/set-anchor/")

        self.assertEqual(response.status_code, 302)
        membership = FamilyMembership.objects.get(family=self.family, user=viewer)
        self.assertIsNone(membership.person)

    def test_tree_json_includes_person_social_context(self):
        story = Story.objects.create(
            family=self.family,
            title="Target Story",
            body="A story about Target.",
            author=self.owner,
        )
        story.people.add(self.target)
        memory = Memory.objects.create(
            family=self.family,
            title="Target Memory",
            memory_type=Memory.Type.PHOTO,
            uploaded_by=self.owner,
        )
        memory.people.add(self.target)
        Activity.objects.create(
            family=self.family,
            actor=self.owner,
            activity_type=Activity.Type.STORY_ADDED,
            message="Published Target Story",
            story=story,
        )
        self.client.force_login(self.owner)

        response = self.client.get("/tree/")
        target_data = self._tree_person_data(response, self.target)

        self.assertEqual(target_data["social"]["story_count"], 1)
        self.assertEqual(target_data["social"]["memory_count"], 1)
        self.assertEqual(
            target_data["social"]["recent_activity"][0]["message"],
            "Published Target Story",
        )

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

    def test_tree_invite_relative_endpoint_creates_living_parent(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            f"/tree/people/{self.anchor.id}/invite-relative/parent/",
            {
                "first_name": "Living",
                "last_name": "Parent",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": "",
                "is_living": "True",
                "death_date": "",
                "invitee": "",
                "role": FamilyMembership.Role.MEMBER,
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Relative added")
        parent = Person.objects.get(first_name="Living", last_name="Parent")
        self.assertTrue(parent.is_living)
        self.assertIsNone(parent.death_date)

    def test_tree_invite_relative_endpoint_creates_deceased_parent_with_death_date(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            f"/tree/people/{self.anchor.id}/invite-relative/parent/",
            {
                "first_name": "Late",
                "last_name": "Parent",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": "",
                "is_living": "False",
                "death_date": "2009-03-12",
                "invitee": "",
                "role": FamilyMembership.Role.MEMBER,
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Relative added")
        parent = Person.objects.get(first_name="Late", last_name="Parent")
        self.assertFalse(parent.is_living)
        self.assertEqual(parent.death_date, date(2009, 3, 12))

    def test_tree_invite_relative_endpoint_creates_deceased_sibling_without_death_date(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            f"/tree/people/{self.anchor.id}/invite-relative/sibling/",
            {
                "first_name": "Late",
                "last_name": "Sibling",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": "",
                "is_living": "False",
                "death_date": "",
                "invitee": "",
                "role": FamilyMembership.Role.MEMBER,
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Relative added")
        sibling = Person.objects.get(first_name="Late", last_name="Sibling")
        self.assertFalse(sibling.is_living)
        self.assertIsNone(sibling.death_date)

    def test_tree_invite_relative_endpoint_rejects_living_person_with_death_date(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            f"/tree/people/{self.anchor.id}/invite-relative/child/",
            {
                "first_name": "Invalid",
                "last_name": "Dates",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": "",
                "is_living": "True",
                "death_date": "2009-03-12",
                "invitee": "",
                "role": FamilyMembership.Role.MEMBER,
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mark this relative as deceased")
        self.assertFalse(Person.objects.filter(first_name="Invalid", last_name="Dates").exists())

    def test_tree_invite_relative_endpoint_rejects_invite_for_deceased_relative(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            f"/tree/people/{self.anchor.id}/invite-relative/child/",
            {
                "first_name": "No",
                "last_name": "Invite",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": "",
                "is_living": "False",
                "death_date": "",
                "invitee": "late@example.com",
                "role": FamilyMembership.Role.MEMBER,
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Deceased relatives cannot be invited")
        self.assertFalse(Person.objects.filter(first_name="No", last_name="Invite").exists())
        self.assertFalse(FamilyInvitation.objects.filter(invitee_email="late@example.com").exists())

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

    def test_tree_invite_relative_endpoint_can_add_child_with_other_parent(self):
        partner = Person.objects.create(
            family=self.family,
            first_name="Known",
            last_name="Partner",
            created_by=self.owner,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.anchor,
            to_person=partner,
            relationship_type=Relationship.Type.SPOUSE,
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            f"/tree/people/{self.anchor.id}/invite-relative/child/",
            {
                "first_name": "Two",
                "last_name": "Parents",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": "",
                "other_parent": str(partner.id),
                "invitee": "",
                "role": FamilyMembership.Role.MEMBER,
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        child = Person.objects.get(first_name="Two", last_name="Parents")
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=partner,
                to_person=child,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )

    def test_tree_invite_relative_endpoint_can_add_sibling_with_shared_parent(self):
        parent = Person.objects.create(
            family=self.family,
            first_name="Shared",
            last_name="Parent",
            created_by=self.owner,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=parent,
            to_person=self.anchor,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            f"/tree/people/{self.anchor.id}/invite-relative/sibling/",
            {
                "first_name": "Shared",
                "last_name": "Sibling",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": "",
                "shared_parents": [str(parent.id)],
                "invitee": "",
                "role": FamilyMembership.Role.MEMBER,
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        sibling = Person.objects.get(first_name="Shared", last_name="Sibling")
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=parent,
                to_person=sibling,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )

    def test_tree_invite_relative_endpoint_can_add_step_parent(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            f"/tree/people/{self.anchor.id}/invite-relative/parent/",
            {
                "first_name": "Step",
                "last_name": "Parent",
                "gender": Person.Gender.UNKNOWN,
                "birth_date": "",
                "parent_relationship_type": Relationship.Type.STEP_PARENT,
                "invitee": "",
                "role": FamilyMembership.Role.MEMBER,
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        parent = Person.objects.get(first_name="Step", last_name="Parent")
        self.assertTrue(
            Relationship.objects.filter(
                family=self.family,
                from_person=parent,
                to_person=self.anchor,
                relationship_type=Relationship.Type.STEP_PARENT,
            ).exists()
        )

    def test_tree_invite_relative_sheet_shows_context_fields(self):
        partner = Person.objects.create(
            family=self.family,
            first_name="Known",
            last_name="Partner",
            created_by=self.owner,
        )
        parent = Person.objects.create(
            family=self.family,
            first_name="Known",
            last_name="Parent",
            created_by=self.owner,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.anchor,
            to_person=partner,
            relationship_type=Relationship.Type.SPOUSE,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=parent,
            to_person=self.anchor,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        self.client.force_login(self.owner)

        child_response = self.client.get(f"/tree/people/{self.anchor.id}/invite-relative/child/")
        sibling_response = self.client.get(f"/tree/people/{self.anchor.id}/invite-relative/sibling/")
        parent_response = self.client.get(f"/tree/people/{self.anchor.id}/invite-relative/parent/")
        partner_response = self.client.get(f"/tree/people/{self.anchor.id}/invite-relative/partner/")

        self.assertContains(child_response, "Other parent")
        self.assertContains(child_response, "Known Partner")
        self.assertContains(sibling_response, "Shared parents")
        self.assertContains(sibling_response, "Known Parent")
        self.assertContains(parent_response, "Step-parent")
        self.assertContains(partner_response, "Ex-partner")

    def test_tree_detail_menu_always_shows_add_relative_actions(self):
        partner = Person.objects.create(
            family=self.family,
            first_name="Existing",
            last_name="Partner",
            created_by=self.owner,
        )
        child = Person.objects.create(
            family=self.family,
            first_name="Existing",
            last_name="Child",
            created_by=self.owner,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.anchor,
            to_person=partner,
            relationship_type=Relationship.Type.SPOUSE,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.anchor,
            to_person=child,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        self.client.force_login(self.owner)

        response = self.client.get("/tree/")

        self.assertContains(response, 'data-detail-menu-toggle aria-expanded="false"')
        self.assertContains(response, 'id="detail-relation-picker"')
        self.assertContains(response, 'data-detail-action="add_parent"')
        self.assertContains(response, 'data-detail-action="add_partner"')
        self.assertContains(response, 'data-detail-action="add_child"')
        self.assertContains(response, 'data-detail-action="add_sibling"')

    def test_parent_card_can_open_add_sibling_sheet(self):
        father = Person.objects.create(
            family=self.family,
            first_name="Father",
            last_name="Person",
            created_by=self.owner,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=father,
            to_person=self.anchor,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        self.client.force_login(self.owner)

        response = self.client.get("/tree/")
        father_data = self._tree_person_data(response, father)

        self.assertTrue(father_data["can_add_relative"])
        self.assertEqual(
            father_data["urls"]["add_relative"]["sibling"],
            f"/tree/people/{father.id}/invite-relative/sibling/",
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


class InviteRelativeFormTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="formowner",
            email="formowner@example.com",
            password="secret",
        )
        self.family = Family.objects.create(
            name="Form Family", slug="form-family", created_by=self.owner
        )
        self.anchor = Person.objects.create(
            family=self.family,
            first_name="Anchor",
            last_name="Person",
            created_by=self.owner,
        )

    def _sibling_post_data(self, shared_parent_ids=None):
        data = {
            "first_name": "New",
            "last_name": "Sibling",
            "gender": Person.Gender.UNKNOWN,
            "birth_date": "",
            "invitee": "",
            "role": FamilyMembership.Role.MEMBER,
            "message": "",
        }
        if shared_parent_ids is not None:
            data["shared_parents"] = shared_parent_ids
        return data

    def test_parents_for_person_includes_parents_of_siblings(self):
        parent = Person.objects.create(
            family=self.family,
            first_name="Shared",
            last_name="Parent",
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
            from_person=parent,
            to_person=sibling,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=self.anchor,
            to_person=sibling,
            relationship_type=Relationship.Type.SIBLING,
        )

        form = InviteRelativeForm(
            data=self._sibling_post_data(shared_parent_ids=[str(parent.id)]),
            family=self.family,
            anchor_person=self.anchor,
            relation_type="sibling",
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_sibling_form_requires_shared_parent_when_candidates_exist(self):
        parent = Person.objects.create(
            family=self.family,
            first_name="Shared",
            last_name="Parent",
            created_by=self.owner,
        )
        Relationship.objects.create(
            family=self.family,
            from_person=parent,
            to_person=self.anchor,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

        form = InviteRelativeForm(
            data=self._sibling_post_data(shared_parent_ids=[]),
            family=self.family,
            anchor_person=self.anchor,
            relation_type="sibling",
        )
        self.assertFalse(form.is_valid())
        self.assertIn("shared_parents", form.errors)

    def test_sibling_form_allows_no_shared_parent_when_no_candidates(self):
        form = InviteRelativeForm(
            data=self._sibling_post_data(shared_parent_ids=[]),
            family=self.family,
            anchor_person=self.anchor,
            relation_type="sibling",
        )
        self.assertTrue(form.is_valid(), form.errors)
