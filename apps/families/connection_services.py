from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.families.models import FamilyAuditLog, FamilyConnectionRequest, FamilyMembership
from apps.families.public_discovery import manager_can_review_requests


@transaction.atomic
def create_connection_request(*, family, user, cleaned_data, suggestion=None):
    if not family.allow_connection_requests:
        raise ValidationError("This family tree is not accepting requests right now.")
    suggestion = suggestion or {}
    request_obj = FamilyConnectionRequest(
        family=family,
        user=user,
        suggested_person=suggestion.get("person"),
        first_name=cleaned_data["first_name"].strip(),
        middle_name=(cleaned_data.get("middle_name") or "").strip(),
        last_name=cleaned_data["last_name"].strip(),
        maiden_name=(cleaned_data.get("maiden_name") or "").strip(),
        birth_date=cleaned_data.get("birth_date"),
        parent_clue=(cleaned_data.get("parent_clue") or "").strip(),
        grandparent_clue=(cleaned_data.get("grandparent_clue") or "").strip(),
        region_clue=(cleaned_data.get("region_clue") or "").strip(),
        connection_type=cleaned_data.get("connection_type") or FamilyConnectionRequest.ConnectionType.IN_FAMILY,
        requester_message=(cleaned_data.get("requester_message") or "").strip(),
        match_score=suggestion.get("score") or 0,
        match_reasons=suggestion.get("reasons") or [],
    )
    request_obj.full_clean()
    request_obj.save()
    _audit(family=family, actor=user, action="connection_request.created", obj=request_obj)
    return request_obj


@transaction.atomic
def approve_connection_request(request_obj, reviewer):
    if not manager_can_review_requests(request_obj.family, reviewer):
        raise PermissionDenied("You do not have permission to approve this request.")
    if request_obj.status != FamilyConnectionRequest.Status.PENDING:
        raise ValidationError("This request is no longer pending.")
    membership, _created = FamilyMembership.objects.get_or_create(
        family=request_obj.family,
        user=request_obj.user,
        defaults={"role": FamilyMembership.Role.MEMBER},
    )
    if request_obj.suggested_person_id:
        already_linked = FamilyMembership.objects.filter(
            family=request_obj.family,
            person=request_obj.suggested_person,
        ).exclude(user=request_obj.user).exists()
        if already_linked:
            raise ValidationError("That profile is already linked to another account.")
        membership.person = request_obj.suggested_person
    membership.role = _stronger_role(membership.role, FamilyMembership.Role.MEMBER)
    membership.full_clean()
    membership.save()
    request_obj.status = FamilyConnectionRequest.Status.APPROVED
    request_obj.reviewed_by = reviewer
    request_obj.reviewed_at = timezone.now()
    request_obj.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    _audit(family=request_obj.family, actor=reviewer, action="connection_request.approved", obj=request_obj)
    return membership


@transaction.atomic
def reject_connection_request(request_obj, reviewer, reviewer_note=""):
    if not manager_can_review_requests(request_obj.family, reviewer):
        raise PermissionDenied("You do not have permission to reject this request.")
    if request_obj.status != FamilyConnectionRequest.Status.PENDING:
        raise ValidationError("This request is no longer pending.")
    request_obj.status = FamilyConnectionRequest.Status.REJECTED
    request_obj.reviewed_by = reviewer
    request_obj.reviewer_note = reviewer_note or ""
    request_obj.reviewed_at = timezone.now()
    request_obj.save(update_fields=["status", "reviewed_by", "reviewer_note", "reviewed_at", "updated_at"])
    _audit(family=request_obj.family, actor=reviewer, action="connection_request.rejected", obj=request_obj)
    return request_obj


def _stronger_role(existing_role, new_role):
    priority = [
        FamilyMembership.Role.VIEWER,
        FamilyMembership.Role.MEMBER,
        FamilyMembership.Role.CONTRIBUTOR,
        FamilyMembership.Role.BRANCH_ADMIN,
        FamilyMembership.Role.ADMIN,
        FamilyMembership.Role.OWNER,
    ]
    return max([existing_role, new_role], key=priority.index)


def _audit(*, family, actor, action, obj=None):
    FamilyAuditLog.objects.create(
        family=family,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        object_type=obj.__class__.__name__ if obj else "",
        object_id=getattr(obj, "id", None),
    )
