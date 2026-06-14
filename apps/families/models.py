from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.relationships.models import Relationship


class Family(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="families_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "families"
        ordering = ["name"]

    def __str__(self):
        return self.name


class FamilyMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
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
