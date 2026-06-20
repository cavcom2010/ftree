from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import get_random_string

from apps.relationships.models import Relationship


def make_email_verification_token():
    return get_random_string(64)


def make_share_token():
    return get_random_string(48)


def default_email_verification_expiry():
    return timezone.now() + timedelta(hours=24)


def default_invite_link_expiry():
    return timezone.now() + timedelta(days=30)


class Family(models.Model):
    class Visibility(models.TextChoices):
        PRIVATE = "private", "Private"
        DISCOVERABLE = "discoverable", "Discoverable"
        PUBLIC_ANCESTORS = "public_ancestors", "Public ancestors only"
        PUBLIC_SHOWCASE = "public_showcase", "Public showcase"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="families_created",
    )
    visibility = models.CharField(
        max_length=30,
        choices=Visibility.choices,
        default=Visibility.PRIVATE,
        db_index=True,
        help_text="Controls how this tree appears in public discovery.",
    )
    public_summary = models.TextField(
        blank=True,
        default="",
        help_text="Short public-safe description shown on discovery pages.",
    )
    origin_summary = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Public-safe origin text, for example Zimbabwe · UK · South Africa.",
    )
    main_surnames = models.JSONField(default=list, blank=True)
    maiden_surnames = models.JSONField(
        default=list,
        blank=True,
        help_text="Used for private matching and safe discovery. Do not expose living people's maiden names by default.",
    )
    regions = models.JSONField(default=list, blank=True)
    allow_connection_requests = models.BooleanField(default=True)
    allow_public_surname_search = models.BooleanField(default=True)
    show_public_tree_shape = models.BooleanField(
        default=True,
        help_text="When enabled, public visitors can see the shape of this tree with private placeholders.",
    )
    show_living_private_placeholders = models.BooleanField(
        default=True,
        help_text="Shows anonymised living-person nodes instead of removing them from public trees.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "families"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["visibility", "slug"]),
            models.Index(fields=["allow_public_surname_search"]),
        ]

    def __str__(self):
        return self.name

    @property
    def is_publicly_listed(self):
        return self.visibility in {
            self.Visibility.DISCOVERABLE,
            self.Visibility.PUBLIC_ANCESTORS,
            self.Visibility.PUBLIC_SHOWCASE,
        }

    @property
    def public_origin_label(self):
        if self.origin_summary:
            return self.origin_summary
        regions = [str(region).strip() for region in self.regions if str(region).strip()]
        return " · ".join(regions[:3])


class FamilyMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        BRANCH_ADMIN = "branch_admin", "Branch admin"
        CONTRIBUTOR = "contributor", "Contributor"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"

    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="family_memberships",
    )
    person = models.ForeignKey(
        "people.Person",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="family_memberships",
        help_text="The family-tree person represented by this user.",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["family", "user"],
                name="unique_family_membership",
            ),
            models.UniqueConstraint(
                fields=["family", "person"],
                condition=Q(person__isnull=False),
                name="unique_claimed_person_per_family",
            ),
        ]
        ordering = ["family", "joined_at"]

    def __str__(self):
        return f"{self.user} in {self.family} as {self.get_role_display()}"

    def clean(self):
        if self.person_id and self.person.family_id != self.family_id:
            raise ValidationError({"person": "Membership person must belong to the same family."})


class FamilyBranch(models.Model):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180)
    root_person = models.ForeignKey(
        "people.Person",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rooted_branches",
    )
    description = models.TextField(blank=True, default="")
    is_public_showcase = models.BooleanField(default=False)
    allow_branch_requests = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="family_branches_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["family", "name"]
        constraints = [
            models.UniqueConstraint(fields=["family", "slug"], name="unique_family_branch_slug"),
        ]

    def __str__(self):
        return f"{self.name} · {self.family.name}"

    def clean(self):
        if self.root_person_id and self.root_person.family_id != self.family_id:
            raise ValidationError({"root_person": "Branch root must belong to the same family."})


class FamilyInviteLink(models.Model):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="invite_links")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="family_invite_links_created",
    )
    role = models.CharField(max_length=20, choices=FamilyMembership.Role.choices, default=FamilyMembership.Role.VIEWER)
    token = models.CharField(max_length=96, unique=True, default=make_share_token)
    note = models.CharField(max_length=255, blank=True, default="")
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    use_count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(default=default_invite_link_expiry)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["token"]), models.Index(fields=["family", "revoked_at"])]

    def __str__(self):
        return f"Invite link for {self.family}"

    @property
    def is_active(self):
        if self.revoked_at:
            return False
        if self.expires_at <= timezone.now():
            return False
        if self.max_uses is not None and self.use_count >= self.max_uses:
            return False
        return True


class EmailVerification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verifications",
    )
    email = models.EmailField()
    token = models.CharField(max_length=96, unique=True, default=make_email_verification_token)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_email_verification_expiry)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"], name="families_em_token_8b8f1a_idx"),
            models.Index(fields=["email"], name="families_em_email_7d6f20_idx"),
            models.Index(fields=["user", "verified_at"], name="families_em_user_02ef8b_idx"),
        ]

    def __str__(self):
        return f"Email verification for {self.email}"

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()

    @property
    def is_verified(self):
        return bool(self.verified_at)

    @property
    def can_verify(self):
        return not self.is_verified and not self.is_expired

    def mark_verified(self):
        self.verified_at = timezone.now()
        self.save(update_fields=["verified_at"])


class FamilyInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        IGNORED = "ignored", "Ignored"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    inviter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="family_invitations_sent",
    )
    invitee_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="family_invitations_received",
    )
    invitee_email = models.EmailField(blank=True, default="")
    person = models.ForeignKey(
        "people.Person",
        on_delete=models.CASCADE,
        related_name="family_invitations",
    )
    anchor_person = models.ForeignKey(
        "people.Person",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="family_invitations_created_from",
    )
    relationship_type = models.CharField(
        max_length=30,
        choices=Relationship.Type.choices,
        blank=True,
        default="",
    )
    role = models.CharField(
        max_length=20,
        choices=FamilyMembership.Role.choices,
        default=FamilyMembership.Role.MEMBER,
    )
    message = models.TextField(blank=True, default="")
    token = models.CharField(max_length=96, unique=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-sent_at"]
        indexes = [
            models.Index(fields=["family", "status"]),
            models.Index(fields=["invitee_email", "status"]),
            models.Index(fields=["token"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "person"],
                condition=Q(status="pending"),
                name="unique_pending_invitation_per_person",
            ),
        ]

    def __str__(self):
        target = self.invitee_user or self.invitee_email or "unassigned invitee"
        return f"{target} invited to {self.family}"

    @property
    def invitee_label(self):
        return self.invitee_user.username if self.invitee_user_id else self.invitee_email

    @property
    def is_pending(self):
        return self.status == self.Status.PENDING and not self.is_expired

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at <= timezone.now())

    def clean(self):
        if not self.invitee_user_id and not self.invitee_email:
            raise ValidationError("Invite must target an existing user or an email address.")
        if self.person_id and self.person.family_id != self.family_id:
            raise ValidationError({"person": "Invited person must belong to the same family."})
        if self.anchor_person_id and self.anchor_person.family_id != self.family_id:
            raise ValidationError({"anchor_person": "Anchor person must belong to the same family."})
        if self.invitee_user_id and self.invitee_email:
            raise ValidationError("Invite cannot target both a user and an email address.")
        if self.relationship_type and self.relationship_type not in Relationship.Type.values:
            raise ValidationError({"relationship_type": "Unknown relationship type."})


class FamilyConnectionRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        NEEDS_MORE_INFO = "needs_more_info", "Needs more information"
        CANCELLED = "cancelled", "Cancelled"

    class ConnectionType(models.TextChoices):
        IN_FAMILY = "in_family", "I am in this family"
        RESEARCHING_SURNAME = "researching_surname", "I am researching this surname"
        RELATED_BY_MARRIAGE = "related_by_marriage", "I am related by marriage"
        BRANCH_OWNER = "branch_owner", "I am the owner of this branch"
        INVITED = "invited", "I was invited by a family member"
        OTHER = "other", "Other"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="connection_requests")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="family_connection_requests",
    )
    suggested_person = models.ForeignKey(
        "people.Person",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connection_requests",
    )
    suggested_branch = models.ForeignKey(
        FamilyBranch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connection_requests",
    )
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, default="")
    last_name = models.CharField(max_length=100)
    maiden_name = models.CharField(max_length=100, blank=True, default="")
    birth_date = models.DateField(null=True, blank=True)
    parent_clue = models.CharField(max_length=255, blank=True, default="")
    grandparent_clue = models.CharField(max_length=255, blank=True, default="")
    region_clue = models.CharField(max_length=255, blank=True, default="")
    connection_type = models.CharField(
        max_length=40,
        choices=ConnectionType.choices,
        default=ConnectionType.IN_FAMILY,
    )
    requester_message = models.TextField(blank=True, default="")
    match_score = models.PositiveIntegerField(default=0)
    match_reasons = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING, db_index=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="family_connection_requests_reviewed",
    )
    reviewer_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["family", "status"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["last_name", "birth_date"]),
        ]

    def __str__(self):
        return f"{self.user} requesting {self.family}"

    @property
    def full_name(self):
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        return " ".join(part for part in parts if part)

    def clean(self):
        if self.suggested_person_id and self.suggested_person.family_id != self.family_id:
            raise ValidationError({"suggested_person": "Suggested person must belong to this family."})
        if self.suggested_branch_id and self.suggested_branch.family_id != self.family_id:
            raise ValidationError({"suggested_branch": "Suggested branch must belong to this family."})


class FamilyEditSuggestion(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="edit_suggestions")
    person = models.ForeignKey("people.Person", on_delete=models.CASCADE, related_name="edit_suggestions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="family_edit_suggestions",
    )
    field_name = models.CharField(max_length=100)
    current_value = models.TextField(blank=True, default="")
    suggested_value = models.TextField()
    reason = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="family_edit_suggestions_reviewed",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["family", "status"]), models.Index(fields=["person", "status"])]

    def __str__(self):
        return f"Suggestion for {self.person}: {self.field_name}"

    def clean(self):
        if self.person_id and self.person.family_id != self.family_id:
            raise ValidationError({"person": "Suggestion person must belong to the same family."})


class FamilyTakedownRequest(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        REVIEWING = "reviewing", "Reviewing"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="takedown_requests")
    person = models.ForeignKey(
        "people.Person",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="takedown_requests",
    )
    reporter_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="family_takedown_requests",
    )
    reporter_email = models.EmailField(blank=True, default="")
    reason = models.CharField(max_length=160)
    details = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["family", "status"]), models.Index(fields=["reporter_email"])]

    def __str__(self):
        return f"Takedown request for {self.family}"

    def clean(self):
        if self.person_id and self.person.family_id != self.family_id:
            raise ValidationError({"person": "Reported person must belong to the same family."})
        if not self.reporter_user_id and not self.reporter_email:
            raise ValidationError("Provide a reporter email or an authenticated reporter.")


class FamilyAuditLog(models.Model):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="family_audit_logs",
    )
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=100, blank=True, default="")
    object_id = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["family", "created_at"]), models.Index(fields=["action"])]

    def __str__(self):
        return f"{self.action} · {self.family}"
