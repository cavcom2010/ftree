import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.families.models import Family, FamilyInvitation, FamilyMembership
from apps.people.models import Person
from apps.relationships.models import Relationship
from apps.social.models import Activity

User = get_user_model()


INVITE_ROLES = {
    FamilyMembership.Role.OWNER,
    FamilyMembership.Role.ADMIN,
    FamilyMembership.Role.MEMBER,
}


PARENT_RELATIONSHIP_TYPES = {
    Relationship.Type.PARENT_CHILD,
    Relationship.Type.ADOPTIVE_PARENT,
    Relationship.Type.STEP_PARENT,
    Relationship.Type.GUARDIAN,
}

PARTNER_RELATIONSHIP_TYPES = {
    Relationship.Type.SPOUSE,
    Relationship.Type.PARTNER,
    Relationship.Type.EX_PARTNER,
}

RELATIONSHIP_DIRECTIONS = {
    "parent": Relationship.Type.PARENT_CHILD,
    "child": Relationship.Type.PARENT_CHILD,
    "partner": Relationship.Type.SPOUSE,
    "spouse": Relationship.Type.SPOUSE,
    "sibling": Relationship.Type.SIBLING,
}


def current_family_for_user(user, family_slug=None):
    if getattr(user, "is_authenticated", False):
        memberships = FamilyMembership.objects.filter(user=user).select_related("family")
        if family_slug:
            membership = memberships.filter(family__slug=family_slug).first()
            if membership:
                return membership.family
        membership = memberships.order_by("joined_at", "family__name").first()
        if membership:
            return membership.family
    if family_slug:
        family = Family.objects.filter(slug=family_slug).first()
        if family:
            return family
    return Family.objects.order_by("name").first()


def membership_for_user(family, user):
    if not family or not getattr(user, "is_authenticated", False):
        return None
    return FamilyMembership.objects.filter(family=family, user=user).select_related("person").first()


def can_invite(family, user):
    membership = membership_for_user(family, user)
    return bool(membership and membership.role in INVITE_ROLES)


def require_invite_permission(family, user):
    if not can_invite(family, user):
        raise PermissionDenied("You do not have permission to invite relatives to this family.")


def resolve_invitee(identifier):
    value = (identifier or "").strip()
    if not value:
        raise ValidationError("Enter a username or email address.")

    user = (
        User.objects.filter(Q(username__iexact=value) | Q(email__iexact=value))
        .order_by("id")
        .first()
    )
    if user:
        return user, user.email or value

    if "@" not in value:
        raise ValidationError("Enter an email address for people who have not signed up yet.")

    return None, value.lower()


def create_invitation(
    *,
    family,
    inviter,
    person,
    invitee_identifier,
    role=FamilyMembership.Role.MEMBER,
    message="",
    anchor_person=None,
    relationship_type="",
):
    require_invite_permission(family, inviter)
    if person.family_id != family.id:
        raise ValidationError("Invited person must belong to this family.")
    if anchor_person and anchor_person.family_id != family.id:
        raise ValidationError("Anchor person must belong to this family.")

    invitee_user, invitee_email = resolve_invitee(invitee_identifier)
    existing_membership = None
    if invitee_user:
        existing_membership = FamilyMembership.objects.filter(family=family, user=invitee_user).first()
        if existing_membership and existing_membership.person_id == person.id:
            raise ValidationError(f"{invitee_user} is already connected to {person.full_name}.")
        if existing_membership and existing_membership.person_id and existing_membership.person_id != person.id:
            raise ValidationError(f"{invitee_user} is already connected to another person in this family.")

    if FamilyMembership.objects.filter(family=family, person=person).exists():
        raise ValidationError(f"{person.full_name} is already connected to a user.")

    duplicate = FamilyInvitation.objects.filter(
        family=family,
        person=person,
        status=FamilyInvitation.Status.PENDING,
    ).first()
    if duplicate:
        raise ValidationError(f"{person.full_name} already has a pending invitation.")

    invitation = FamilyInvitation.objects.create(
        family=family,
        inviter=inviter,
        invitee_user=invitee_user,
        invitee_email=invitee_email or "",
        person=person,
        anchor_person=anchor_person,
        relationship_type=relationship_type or "",
        role=role,
        message=message,
        token=_unique_token(),
        expires_at=timezone.now() + timedelta(days=21),
    )
    Activity.objects.create(
        family=family,
        actor=inviter,
        activity_type=Activity.Type.PERSON_ADDED,
        message=f"Invited {invitation.invitee_label} to claim {person.full_name}",
        person=person,
    )
    return invitation


@transaction.atomic
def create_relative(
    *,
    family,
    inviter,
    anchor_person,
    relation_type,
    person_data,
    parent_relationship_type=Relationship.Type.PARENT_CHILD,
    partner_relationship_type=Relationship.Type.SPOUSE,
    other_parent=None,
    shared_parents=None,
):
    require_invite_permission(family, inviter)
    if anchor_person.family_id != family.id:
        raise ValidationError("Anchor person must belong to this family.")
    if other_parent and other_parent.family_id != family.id:
        raise ValidationError("Other parent must belong to this family.")
    shared_parents = list(shared_parents or [])
    if any(parent.family_id != family.id for parent in shared_parents):
        raise ValidationError("Shared parents must belong to this family.")
    if relation_type == "child" and other_parent and not _people_are_partners(family, anchor_person, other_parent):
        raise ValidationError("Other parent must be a known partner for this person.")
    if relation_type == "sibling":
        valid_parent_ids = _parent_ids_for_person(family, anchor_person)
        if any(parent.id not in valid_parent_ids for parent in shared_parents):
            raise ValidationError("Shared parents must already be parents of this person.")

    person = Person.objects.create(
        family=family,
        created_by=inviter,
        first_name=person_data["first_name"],
        last_name=person_data["last_name"],
        gender=person_data.get("gender") or Person.Gender.UNKNOWN,
        birth_date=person_data.get("birth_date"),
    )
    relationship_type = create_relationship_for_relative(
        family,
        anchor_person,
        person,
        relation_type,
        parent_relationship_type=parent_relationship_type,
        partner_relationship_type=partner_relationship_type,
        other_parent=other_parent,
        shared_parents=shared_parents,
    )
    Activity.objects.create(
        family=family,
        actor=inviter,
        activity_type=Activity.Type.PERSON_ADDED,
        message=f"Added {person.full_name} to the family tree",
        person=person,
    )
    return person, relationship_type


@transaction.atomic
def create_relative_with_optional_invite(
    *,
    family,
    inviter,
    anchor_person,
    relation_type,
    person_data,
    invitee_identifier="",
    role=FamilyMembership.Role.MEMBER,
    message="",
    parent_relationship_type=Relationship.Type.PARENT_CHILD,
    partner_relationship_type=Relationship.Type.SPOUSE,
    other_parent=None,
    shared_parents=None,
):
    person, relationship_type = create_relative(
        family=family,
        inviter=inviter,
        anchor_person=anchor_person,
        relation_type=relation_type,
        person_data=person_data,
        parent_relationship_type=parent_relationship_type,
        partner_relationship_type=partner_relationship_type,
        other_parent=other_parent,
        shared_parents=shared_parents,
    )
    if not (invitee_identifier or "").strip():
        return person, None

    invitation = create_invitation(
        family=family,
        inviter=inviter,
        person=person,
        invitee_identifier=invitee_identifier,
        role=role,
        message=message,
        anchor_person=anchor_person,
        relationship_type=relationship_type,
    )
    return person, invitation


@transaction.atomic
def create_relative_invitation(
    *,
    family,
    inviter,
    anchor_person,
    relation_type,
    person_data,
    invitee_identifier,
    role=FamilyMembership.Role.MEMBER,
    message="",
    parent_relationship_type=Relationship.Type.PARENT_CHILD,
    partner_relationship_type=Relationship.Type.SPOUSE,
    other_parent=None,
    shared_parents=None,
):
    if not (invitee_identifier or "").strip():
        raise ValidationError("Enter a username or email address.")
    person, relationship_type = create_relative(
        family=family,
        inviter=inviter,
        anchor_person=anchor_person,
        relation_type=relation_type,
        person_data=person_data,
        parent_relationship_type=parent_relationship_type,
        partner_relationship_type=partner_relationship_type,
        other_parent=other_parent,
        shared_parents=shared_parents,
    )
    return create_invitation(
        family=family,
        inviter=inviter,
        person=person,
        invitee_identifier=invitee_identifier,
        role=role,
        message=message,
        anchor_person=anchor_person,
        relationship_type=relationship_type,
    )


def create_relationship_for_relative(
    family,
    anchor_person,
    relative,
    relation_type,
    parent_relationship_type=Relationship.Type.PARENT_CHILD,
    partner_relationship_type=Relationship.Type.SPOUSE,
    other_parent=None,
    shared_parents=None,
):
    normalized = relation_type if relation_type in RELATIONSHIP_DIRECTIONS else "child"
    relationship_type = _relationship_type_for_relative(
        normalized,
        parent_relationship_type=parent_relationship_type,
        partner_relationship_type=partner_relationship_type,
    )
    if normalized == "parent":
        from_person, to_person = relative, anchor_person
    else:
        from_person, to_person = anchor_person, relative

    _create_relationship_edge(family, from_person, to_person, relationship_type)
    if normalized == "child" and other_parent:
        _create_relationship_edge(
            family,
            other_parent,
            relative,
            Relationship.Type.PARENT_CHILD,
        )
    if normalized == "sibling":
        for shared_parent in shared_parents or []:
            _create_relationship_edge(
                family,
                shared_parent,
                relative,
                Relationship.Type.PARENT_CHILD,
            )
    return relationship_type


def _relationship_type_for_relative(
    relation_type,
    parent_relationship_type=Relationship.Type.PARENT_CHILD,
    partner_relationship_type=Relationship.Type.SPOUSE,
):
    if relation_type == "parent":
        return (
            parent_relationship_type
            if parent_relationship_type in PARENT_RELATIONSHIP_TYPES
            else Relationship.Type.PARENT_CHILD
        )
    if relation_type in {"partner", "spouse"}:
        return (
            partner_relationship_type
            if partner_relationship_type in PARTNER_RELATIONSHIP_TYPES
            else Relationship.Type.SPOUSE
        )
    return RELATIONSHIP_DIRECTIONS.get(relation_type, Relationship.Type.PARENT_CHILD)


def _create_relationship_edge(family, from_person, to_person, relationship_type):
    Relationship.objects.get_or_create(
        family=family,
        from_person=from_person,
        to_person=to_person,
        relationship_type=relationship_type,
    )


def _people_are_partners(family, first_person, second_person):
    return Relationship.objects.filter(
        Q(from_person=first_person, to_person=second_person)
        | Q(from_person=second_person, to_person=first_person),
        family=family,
        relationship_type__in=PARTNER_RELATIONSHIP_TYPES,
    ).exists()


def _parent_ids_for_person(family, person):
    return set(
        Relationship.objects.filter(
            family=family,
            to_person=person,
            relationship_type__in=PARENT_RELATIONSHIP_TYPES,
        ).values_list("from_person_id", flat=True)
    )


@transaction.atomic
def accept_invitation(invitation, user):
    _require_pending_invitation_for_user(invitation, user)
    membership, _ = FamilyMembership.objects.get_or_create(
        family=invitation.family,
        user=user,
        defaults={
            "role": invitation.role,
            "person": invitation.person,
        },
    )
    if membership.person_id and membership.person_id != invitation.person_id:
        raise ValidationError("Your account is already connected to another person in this family.")

    membership.role = membership.role or invitation.role
    membership.person = invitation.person
    membership.full_clean()
    membership.save(update_fields=["role", "person"])

    invitation.invitee_user = user
    invitation.status = FamilyInvitation.Status.ACCEPTED
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["invitee_user", "status", "responded_at"])

    Activity.objects.create(
        family=invitation.family,
        actor=user,
        activity_type=Activity.Type.PERSON_ADDED,
        message=f"{user.username} connected as {invitation.person.full_name}",
        person=invitation.person,
    )
    return membership


def decline_invitation(invitation, user):
    _respond_without_membership(invitation, user, FamilyInvitation.Status.DECLINED)


def ignore_invitation(invitation, user):
    _respond_without_membership(invitation, user, FamilyInvitation.Status.IGNORED)


def pending_invitations_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return FamilyInvitation.objects.none()
    query = Q(invitee_user=user)
    if user.email:
        query |= Q(invitee_email__iexact=user.email)
    return (
        FamilyInvitation.objects.filter(query, status=FamilyInvitation.Status.PENDING)
        .select_related("family", "person", "inviter")
        .order_by("-sent_at")
    )


def invitation_counts_for_people(family, people):
    person_ids = [person.id for person in people]
    invitations = FamilyInvitation.objects.filter(
        family=family,
        person_id__in=person_ids,
        status=FamilyInvitation.Status.PENDING,
    ).select_related("invitee_user")
    return {invitation.person_id: invitation for invitation in invitations}


def memberships_by_person(family, people):
    person_ids = [person.id for person in people]
    memberships = FamilyMembership.objects.filter(
        family=family,
        person_id__in=person_ids,
    ).select_related("user", "person")
    return {membership.person_id: membership for membership in memberships}


def connected_users_for_family(family):
    return User.objects.filter(
        family_memberships__family=family,
        family_memberships__person__isnull=False,
    ).distinct()


def _respond_without_membership(invitation, user, status):
    _require_pending_invitation_for_user(invitation, user)
    invitation.invitee_user = invitation.invitee_user or user
    invitation.status = status
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["invitee_user", "status", "responded_at"])


def _require_pending_invitation_for_user(invitation, user):
    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Sign in to respond to this invitation.")
    if invitation.status != FamilyInvitation.Status.PENDING:
        raise ValidationError("This invitation is no longer pending.")
    if invitation.is_expired:
        invitation.status = FamilyInvitation.Status.EXPIRED
        invitation.save(update_fields=["status"])
        raise ValidationError("This invitation has expired.")
    if invitation.invitee_user_id and invitation.invitee_user_id != user.id:
        raise PermissionDenied("This invitation is for another user.")
    if invitation.invitee_email and user.email and invitation.invitee_email.lower() != user.email.lower():
        raise PermissionDenied("This invitation is for another email address.")
    if invitation.invitee_email and not user.email and not invitation.invitee_user_id:
        raise PermissionDenied("Add an email address to your account before accepting this invitation.")


def _unique_token():
    while True:
        token = secrets.token_urlsafe(32)
        if not FamilyInvitation.objects.filter(token=token).exists():
            return token
