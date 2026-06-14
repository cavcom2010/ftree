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
):
    require_invite_permission(family, inviter)
    if anchor_person.family_id != family.id:
        raise ValidationError("Anchor person must belong to this family.")

    person = Person.objects.create(
        family=family,
        created_by=inviter,
        first_name=person_data["first_name"],
        last_name=person_data["last_name"],
        gender=person_data.get("gender") or Person.Gender.UNKNOWN,
        birth_date=person_data.get("birth_date"),
    )
    relationship_type = create_relationship_for_relative(family, anchor_person, person, relation_type)
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
):
    person, relationship_type = create_relative(
        family=family,
        inviter=inviter,
        anchor_person=anchor_person,
        relation_type=relation_type,
        person_data=person_data,
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
):
    if not (invitee_identifier or "").strip():
        raise ValidationError("Enter a username or email address.")
    person, relationship_type = create_relative(
        family=family,
        inviter=inviter,
        anchor_person=anchor_person,
        relation_type=relation_type,
        person_data=person_data,
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


def create_relationship_for_relative(family, anchor_person, relative, relation_type):
    normalized = relation_type if relation_type in RELATIONSHIP_DIRECTIONS else "child"
    relationship_type = RELATIONSHIP_DIRECTIONS[normalized]
    if normalized == "parent":
        from_person, to_person = relative, anchor_person
    else:
        from_person, to_person = anchor_person, relative

    Relationship.objects.get_or_create(
        family=family,
        from_person=from_person,
        to_person=to_person,
        relationship_type=relationship_type,
    )
    return relationship_type


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
