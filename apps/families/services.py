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
    Relationship.Type.CO_PARENT,
}

RELATIONSHIP_DIRECTIONS = {
    "parent": Relationship.Type.PARENT_CHILD,
    "child": Relationship.Type.PARENT_CHILD,
    "partner": Relationship.Type.SPOUSE,
    "spouse": Relationship.Type.SPOUSE,
    "sibling": Relationship.Type.SIBLING,
}


def current_family_for_user(user, family_slug=None):
    if not getattr(user, "is_authenticated", False):
        return None

    memberships = FamilyMembership.objects.filter(user=user).select_related("family")
    if family_slug:
        membership = memberships.filter(family__slug=family_slug).first()
        if membership:
            return membership.family
        return None

    membership = memberships.order_by("joined_at", "family__name").first()
    if membership:
        return membership.family
    return None


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
    if not person.is_living:
        raise ValidationError("Deceased relatives cannot be invited to claim an account.")
    if anchor_person and anchor_person.family_id != family.id:
        raise ValidationError("Anchor person must belong to this family.")

    invitee_user, invitee_email = resolve_invitee(invitee_identifier)
    existing_membership = None
    if invitee_user:
        existing_membership = FamilyMembership.objects.filter(family=family, user=invitee_user).first()
        if existing_membership and existing_membership.person_id == person.id:
            raise ValidationError("This user is already linked to that person in this family.")
        if existing_membership and existing_membership.person_id:
            raise ValidationError("This user is already linked to another person in this family.")
    if FamilyInvitation.objects.filter(family=family, person=person, status=FamilyInvitation.Status.PENDING).exists():
        raise ValidationError("This person already has a pending invitation.")

    invitation = FamilyInvitation(
        family=family,
        inviter=inviter,
        invitee_user=invitee_user,
        invitee_email="" if invitee_user else invitee_email,
        person=person,
        anchor_person=anchor_person,
        relationship_type=relationship_type,
        role=role,
        message=message,
        token=secrets.token_urlsafe(32),
        expires_at=timezone.now() + timedelta(days=14),
    )
    invitation.full_clean()
    invitation.save()
    _record_activity(
        family=family,
        user=inviter,
        verb="invited",
        target=person,
        description=f"Invited {invitation.invitee_label} to claim {person.full_name}.",
    )
    return invitation


def accept_invitation(invitation, user):
    if not invitation.is_pending:
        raise ValidationError("This invitation is no longer active.")
    if invitation.invitee_user and invitation.invitee_user_id != user.id:
        raise PermissionDenied("This invitation belongs to another user.")
    if invitation.invitee_email and user.email and invitation.invitee_email.lower() != user.email.lower():
        raise PermissionDenied("Sign in with the invited email address to accept this invitation.")

    with transaction.atomic():
        membership, created = FamilyMembership.objects.get_or_create(
            family=invitation.family,
            user=user,
            defaults={"role": invitation.role, "person": invitation.person},
        )
        if not created:
            if membership.person_id and membership.person_id != invitation.person_id:
                raise ValidationError("Your account is already linked to another person in this family.")
            membership.role = _strongest_role(membership.role, invitation.role)
            membership.person = invitation.person
            membership.full_clean()
            membership.save(update_fields=["role", "person"])
        invitation.status = FamilyInvitation.Status.ACCEPTED
        invitation.invitee_user = user
        invitation.responded_at = timezone.now()
        invitation.save(update_fields=["status", "invitee_user", "responded_at"])
    _record_activity(
        family=invitation.family,
        user=user,
        verb="joined",
        target=invitation.person,
        description=f"{user.get_username()} joined as {invitation.person.full_name}.",
    )
    return membership


def decline_invitation(invitation, user):
    return _respond_to_invitation(invitation, user, FamilyInvitation.Status.DECLINED)


def ignore_invitation(invitation, user):
    return _respond_to_invitation(invitation, user, FamilyInvitation.Status.IGNORED)


def _respond_to_invitation(invitation, user, status):
    if not invitation.is_pending:
        raise ValidationError("This invitation is no longer active.")
    if invitation.invitee_user and invitation.invitee_user_id != user.id:
        raise PermissionDenied("This invitation belongs to another user.")
    if invitation.invitee_email and user.email and invitation.invitee_email.lower() != user.email.lower():
        raise PermissionDenied("Sign in with the invited email address to respond to this invitation.")
    invitation.status = status
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["status", "responded_at"])
    return invitation


def pending_invitations_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return FamilyInvitation.objects.none()
    user_email = (user.email or "").lower()
    invitations = FamilyInvitation.objects.filter(status=FamilyInvitation.Status.PENDING)
    query = Q(invitee_user=user)
    if user_email:
        query |= Q(invitee_email__iexact=user_email)
    return invitations.filter(query).select_related("family", "person", "inviter").order_by("-sent_at")


def memberships_by_person(family, people=None):
    person_ids = [person.id for person in people] if people is not None else None
    queryset = FamilyMembership.objects.filter(family=family, person__isnull=False).select_related("user", "person")
    if person_ids is not None:
        queryset = queryset.filter(person_id__in=person_ids)
    return {membership.person_id: membership for membership in queryset}


def invitation_counts_for_people(family, people=None):
    person_ids = [person.id for person in people] if people is not None else None
    queryset = FamilyInvitation.objects.filter(family=family, status=FamilyInvitation.Status.PENDING)
    if person_ids is not None:
        queryset = queryset.filter(person_id__in=person_ids)
    counts = {}
    for invitation in queryset:
        counts[invitation.person_id] = counts.get(invitation.person_id, 0) + 1
    return counts


def pending_invitations_by_person(family, people):
    person_ids = [p.id for p in people]
    return {
        inv.person_id: inv
        for inv in FamilyInvitation.objects.filter(
            family=family,
            status=FamilyInvitation.Status.PENDING,
            person_id__in=person_ids,
        ).select_related("invitee_user")
    }


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
    parent_relationship_type=None,
    partner_relationship_type=None,
    other_parent=None,
    shared_parents=None,
    partner_shared_children=None,
    parent_shared_children=None,
    existing_person=None,
):
    with transaction.atomic():
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
            partner_shared_children=partner_shared_children,
            parent_shared_children=parent_shared_children,
            existing_person=existing_person,
        )
        invitation = None
        if invitee_identifier:
            if not person.is_living:
                raise ValidationError("Deceased relatives cannot be invited to claim an account.")
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
    parent_relationship_type=None,
    partner_relationship_type=None,
    other_parent=None,
    shared_parents=None,
    partner_shared_children=None,
    parent_shared_children=None,
    existing_person=None,
):
    person, invitation = create_relative_with_optional_invite(
        family=family,
        inviter=inviter,
        anchor_person=anchor_person,
        relation_type=relation_type,
        person_data=person_data,
        invitee_identifier=invitee_identifier,
        role=role,
        message=message,
        parent_relationship_type=parent_relationship_type,
        partner_relationship_type=partner_relationship_type,
        other_parent=other_parent,
        shared_parents=shared_parents,
        partner_shared_children=partner_shared_children,
        parent_shared_children=parent_shared_children,
        existing_person=existing_person,
    )
    return invitation


def create_relative(
    *,
    family,
    inviter,
    anchor_person,
    relation_type,
    person_data,
    parent_relationship_type=None,
    partner_relationship_type=None,
    other_parent=None,
    shared_parents=None,
    partner_shared_children=None,
    parent_shared_children=None,
    existing_person=None,
):
    require_invite_permission(family, inviter)
    if anchor_person.family_id != family.id:
        raise ValidationError("Anchor person must belong to this family.")
    if relation_type not in RELATIONSHIP_DIRECTIONS:
        raise ValidationError("Choose a valid relationship type.")

    person_data = person_data or {}
    person = existing_person
    if person:
        _validate_existing_person_connection(family, anchor_person, person, relation_type)
    else:
        is_living = _coerce_is_living(person_data.get("is_living"))
        death_date = person_data.get("death_date")
        if is_living and death_date:
            raise ValidationError("Mark this relative as deceased before adding a death date.")
        person = Person(
            family=family,
            created_by=inviter,
            first_name=person_data.get("first_name", "").strip(),
            last_name=person_data.get("last_name", "").strip(),
            maiden_name=person_data.get("maiden_name", "").strip(),
            gender=person_data.get("gender") or Person.Gender.UNKNOWN,
            birth_date=person_data.get("birth_date"),
            is_living=is_living,
            death_date=death_date,
        )
        person.full_clean()
        person.save()

    relationship_type = _relationship_type_for_relation(
        relation_type,
        parent_relationship_type=parent_relationship_type,
        partner_relationship_type=partner_relationship_type,
    )
    if existing_person and relation_type in {"partner", "spouse"}:
        relationship_type = (
            _existing_partner_relationship_type(family, anchor_person, person)
            or (
                relationship_type
                if partner_relationship_type in PARTNER_RELATIONSHIP_TYPES
                else Relationship.Type.CO_PARENT
            )
        )
    relationships = _relationships_for_new_relative(
        family=family,
        anchor_person=anchor_person,
        new_person=person,
        relation_type=relation_type,
        relationship_type=relationship_type,
        other_parent=other_parent,
        shared_parents=shared_parents,
        partner_shared_children=partner_shared_children,
        parent_shared_children=parent_shared_children,
    )
    for relationship in relationships:
        _save_relationship_if_missing(relationship)
    _record_activity(
        family=family,
        user=inviter,
        verb="added",
        target=person,
        description=(
            f"Connected {person.full_name} as a {relation_type} of {anchor_person.full_name}."
            if existing_person
            else f"Added {person.full_name} as a {relation_type} of {anchor_person.full_name}."
        ),
    )
    return person, relationship_type


def _coerce_is_living(value):
    if value is None:
        return True
    return value in {True, "True", "true", "1", 1}


def _relationship_type_for_relation(relation_type, parent_relationship_type=None, partner_relationship_type=None):
    if relation_type == "parent":
        return parent_relationship_type if parent_relationship_type in PARENT_RELATIONSHIP_TYPES else Relationship.Type.PARENT_CHILD
    if relation_type in {"partner", "spouse"}:
        return partner_relationship_type if partner_relationship_type in PARTNER_RELATIONSHIP_TYPES else Relationship.Type.SPOUSE
    return RELATIONSHIP_DIRECTIONS[relation_type]


def _relationships_for_new_relative(
    *,
    family,
    anchor_person,
    new_person,
    relation_type,
    relationship_type,
    other_parent=None,
    shared_parents=None,
    partner_shared_children=None,
    parent_shared_children=None,
):
    relationships = []
    if relation_type == "parent":
        relationships.append(
            Relationship(
                family=family,
                from_person=new_person,
                to_person=anchor_person,
                relationship_type=relationship_type,
            )
        )
        for sibling in parent_shared_children or []:
            _validate_known_sibling(family, anchor_person, sibling)
            relationships.append(
                Relationship(
                    family=family,
                    from_person=new_person,
                    to_person=sibling,
                    relationship_type=relationship_type,
                )
            )
    elif relation_type == "child":
        relationships.append(
            Relationship(
                family=family,
                from_person=anchor_person,
                to_person=new_person,
                relationship_type=relationship_type,
            )
        )
        if other_parent:
            _validate_known_partner(family, anchor_person, other_parent)
            relationships.append(
                Relationship(
                    family=family,
                    from_person=other_parent,
                    to_person=new_person,
                    relationship_type=Relationship.Type.PARENT_CHILD,
                )
            )
    elif relation_type in {"partner", "spouse"}:
        relationships.append(
            Relationship(
                family=family,
                from_person=anchor_person,
                to_person=new_person,
                relationship_type=relationship_type,
            )
        )
        for child in partner_shared_children or []:
            _validate_known_child(family, anchor_person, child)
            relationships.append(
                Relationship(
                    family=family,
                    from_person=new_person,
                    to_person=child,
                    relationship_type=Relationship.Type.PARENT_CHILD,
                )
            )
    elif relation_type == "sibling":
        relationships.append(
            Relationship(
                family=family,
                from_person=anchor_person,
                to_person=new_person,
                relationship_type=relationship_type,
            )
        )
        for parent in shared_parents or []:
            _validate_shared_parent(family, anchor_person, parent)
            relationships.append(
                Relationship(
                    family=family,
                    from_person=parent,
                    to_person=new_person,
                    relationship_type=Relationship.Type.PARENT_CHILD,
                )
            )
    return relationships


def _validate_known_partner(family, anchor_person, other_parent):
    if other_parent.family_id != family.id:
        raise ValidationError("Other parent must belong to this family.")
    is_partner = Relationship.objects.filter(
        family=family,
        relationship_type__in=PARTNER_RELATIONSHIP_TYPES,
    ).filter(
        Q(from_person=anchor_person, to_person=other_parent)
        | Q(from_person=other_parent, to_person=anchor_person)
    ).exists()
    if not is_partner:
        raise ValidationError("Other parent must be a known partner of this person.")


def _validate_existing_person_connection(family, anchor_person, existing_person, relation_type):
    if existing_person.family_id != family.id:
        raise ValidationError("Existing person must belong to this family.")
    if existing_person.id == anchor_person.id:
        raise ValidationError("A person cannot be connected to themself.")
    if relation_type in {"partner", "spouse"}:
        if _is_parent_child_between(family, anchor_person, existing_person):
            raise ValidationError("A partner or co-parent cannot be a direct parent or child of this person.")
        if _is_known_sibling(family, anchor_person, existing_person):
            raise ValidationError("A partner or co-parent cannot be a sibling of this person.")


def _existing_partner_relationship_type(family, person, partner):
    relationship = (
        Relationship.objects.filter(
            family=family,
            relationship_type__in=PARTNER_RELATIONSHIP_TYPES,
        )
        .filter(
            Q(from_person=person, to_person=partner)
            | Q(from_person=partner, to_person=person)
        )
        .order_by("created_at", "id")
        .first()
    )
    return relationship.relationship_type if relationship else ""


def _save_relationship_if_missing(relationship):
    existing = Relationship.objects.filter(
        family=relationship.family,
        from_person=relationship.from_person,
        to_person=relationship.to_person,
        relationship_type=relationship.relationship_type,
    ).first()
    if existing:
        return existing

    if relationship.relationship_type in Relationship.SYMMETRIC_TYPES:
        reverse = Relationship.objects.filter(
            family=relationship.family,
            from_person=relationship.to_person,
            to_person=relationship.from_person,
            relationship_type=relationship.relationship_type,
        ).first()
        if reverse:
            return reverse

    relationship.full_clean()
    relationship.save()
    return relationship


def _validate_shared_parent(family, anchor_person, parent):
    if parent.family_id != family.id:
        raise ValidationError("Shared parents must belong to this family.")
    if not Relationship.objects.filter(
        family=family,
        from_person=parent,
        to_person=anchor_person,
        relationship_type__in=PARENT_RELATIONSHIP_TYPES,
    ).exists():
        raise ValidationError("Shared parents must already be parents or guardians of this person.")


def _validate_known_child(family, anchor_person, child):
    if child.family_id != family.id:
        raise ValidationError("Shared children must belong to this family.")
    if not Relationship.objects.filter(
        family=family,
        from_person=anchor_person,
        to_person=child,
        relationship_type__in=PARENT_RELATIONSHIP_TYPES,
    ).exists():
        raise ValidationError("Shared children must already be children of this person.")


def _is_parent_child_between(family, person, other_person):
    return Relationship.objects.filter(
        family=family,
        relationship_type__in=PARENT_RELATIONSHIP_TYPES,
    ).filter(
        Q(from_person=person, to_person=other_person)
        | Q(from_person=other_person, to_person=person)
    ).exists()


def _validate_known_sibling(family, anchor_person, sibling):
    if sibling.family_id != family.id:
        raise ValidationError("Selected siblings must belong to this family.")
    if sibling.id == anchor_person.id:
        raise ValidationError("Do not select yourself as a sibling.")
    if _is_known_sibling(family, anchor_person, sibling):
        return
    raise ValidationError("Selected children must already be known siblings of this person.")


def _is_known_sibling(family, person, sibling):
    explicit_sibling = Relationship.objects.filter(
        family=family,
        relationship_type=Relationship.Type.SIBLING,
    ).filter(
        Q(from_person=person, to_person=sibling) | Q(from_person=sibling, to_person=person)
    ).exists()
    if explicit_sibling:
        return True

    person_parent_ids = set(
        Relationship.objects.filter(
            family=family,
            to_person=person,
            relationship_type__in=PARENT_RELATIONSHIP_TYPES,
        ).values_list("from_person_id", flat=True)
    )
    if not person_parent_ids:
        return False
    sibling_parent_ids = set(
        Relationship.objects.filter(
            family=family,
            to_person=sibling,
            relationship_type__in=PARENT_RELATIONSHIP_TYPES,
        ).values_list("from_person_id", flat=True)
    )
    return bool(person_parent_ids & sibling_parent_ids)


def _strongest_role(existing_role, invited_role):
    priority = [
        FamilyMembership.Role.VIEWER,
        FamilyMembership.Role.MEMBER,
        FamilyMembership.Role.ADMIN,
        FamilyMembership.Role.OWNER,
    ]
    return max([existing_role, invited_role], key=priority.index)


def _activity_type_for_verb(verb):
    if verb == "added":
        return Activity.Type.PERSON_ADDED
    if verb in {"invited", "joined"}:
        return Activity.Type.PERSON_ADDED
    return Activity.Type.PERSON_ADDED


def _record_activity(*, family, user, verb, target, description):
    data = {
        "family": family,
        "actor": user if getattr(user, "is_authenticated", False) else None,
        "activity_type": _activity_type_for_verb(verb),
        "message": description,
    }
    if isinstance(target, Person):
        data["person"] = target
    Activity.objects.create(**data)
