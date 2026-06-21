import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


def person_profile_photo_upload_path(instance, filename):
    return f"people/profile-photos/{uuid.uuid4()}.jpg"


class Person(models.Model):
    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"
        UNKNOWN = "unknown", "Unknown"

    class Visibility(models.TextChoices):
        PRIVATE = "private", "Private"
        TREE_MEMBERS = "tree_members", "Tree members only"
        PUBLIC_IF_DECEASED = "public_if_deceased", "Public if deceased"
        PUBLIC_SHOWCASE = "public_showcase", "Public showcase"

    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="people",
    )
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, default="")
    last_name = models.CharField(max_length=100)
    maiden_name = models.CharField(max_length=100, blank=True, default="")
    gender = models.CharField(
        max_length=10, choices=Gender.choices, default=Gender.UNKNOWN
    )
    birth_date = models.DateField(null=True, blank=True)
    death_date = models.DateField(null=True, blank=True)
    birth_place = models.CharField(max_length=255, blank=True, default="")
    current_place = models.CharField(max_length=255, blank=True, default="")
    profile_photo = models.ImageField(
        upload_to=person_profile_photo_upload_path,
        null=True,
        blank=True,
    )
    biography = models.TextField(blank=True, default="")
    is_living = models.BooleanField(default=True)
    is_private = models.BooleanField(default=False)
    visibility = models.CharField(
        max_length=30,
        choices=Visibility.choices,
        default=Visibility.PUBLIC_IF_DECEASED,
        db_index=True,
        help_text="Person-level public visibility. Living people and children are still protected by public-safe serializers.",
    )
    public_notes = models.TextField(
        blank=True,
        default="",
        help_text="Optional public-safe notes for ancestor/showcase pages.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="people_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "people"
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "first_name", "last_name", "birth_date"],
                name="unique_person_identity",
            ),
            models.UniqueConstraint(
                fields=["family", "first_name", "last_name"],
                condition=Q(birth_date__isnull=True),
                name="unique_person_identity_no_birth_date",
            ),
        ]
        indexes = [
            models.Index(
                fields=["family", "visibility", "is_living"],
                name="people_pers_family__93d6aa_idx",
            ),
            models.Index(
                fields=["last_name", "maiden_name"],
                name="people_pers_last_na_6af25d_idx",
            ),
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        return " ".join(parts)

    @property
    def is_minor(self):
        if not self.is_living or not self.birth_date:
            return False
        today = timezone.localdate()
        age = (
            today.year
            - self.birth_date.year
            - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        )
        return age < 18

    @property
    def can_be_publicly_identified(self):
        if self.is_private:
            return False
        if self.is_living:
            return False
        if self.is_minor:
            return False
        if self.visibility == self.Visibility.PUBLIC_SHOWCASE:
            return True
        if self.visibility == self.Visibility.PUBLIC_IF_DECEASED and not self.is_living:
            return True
        return False

    @property
    def public_display_name(self):
        if self.can_be_publicly_identified:
            return self.full_name
        if self.is_living:
            return "Private living person"
        return "Private family member"

    @property
    def public_date_label(self):
        if not self.can_be_publicly_identified:
            return "Hidden"
        if self.birth_date and self.death_date:
            return f"{self.birth_date.year}–{self.death_date.year}"
        if self.birth_date:
            return f"Born c. {self.birth_date.year}"
        if self.death_date:
            return f"Died {self.death_date.year}"
        return "Dates unknown"

    def get_children(self):
        """Return direct children via parent-like relationships."""
        from apps.relationships.models import Relationship

        parent_types = {
            Relationship.Type.PARENT_CHILD,
            Relationship.Type.ADOPTIVE_PARENT,
            Relationship.Type.STEP_PARENT,
            Relationship.Type.GUARDIAN,
        }
        child_ids = Relationship.objects.filter(
            family=self.family,
            from_person=self,
            relationship_type__in=parent_types,
        ).values_list("to_person_id", flat=True)
        return Person.objects.filter(id__in=child_ids)

    def get_parents(self):
        """Return parents/guardians via parent-like relationships."""
        from apps.relationships.models import Relationship

        parent_types = {
            Relationship.Type.PARENT_CHILD,
            Relationship.Type.ADOPTIVE_PARENT,
            Relationship.Type.STEP_PARENT,
            Relationship.Type.GUARDIAN,
        }
        parent_ids = Relationship.objects.filter(
            family=self.family,
            to_person=self,
            relationship_type__in=parent_types,
        ).values_list("from_person_id", flat=True)
        return Person.objects.filter(id__in=parent_ids)

    def get_partners(self):
        """Return partners/spouses/co-parents."""
        from apps.relationships.models import Relationship

        partner_types = {
            Relationship.Type.SPOUSE,
            Relationship.Type.PARTNER,
            Relationship.Type.EX_PARTNER,
            Relationship.Type.CO_PARENT,
        }
        outgoing = Relationship.objects.filter(
            family=self.family,
            from_person=self,
            relationship_type__in=partner_types,
        ).values_list("to_person_id", flat=True)
        incoming = Relationship.objects.filter(
            family=self.family,
            to_person=self,
            relationship_type__in=partner_types,
        ).values_list("from_person_id", flat=True)
        return Person.objects.filter(id__in=set(outgoing) | set(incoming))

    def get_siblings(self):
        """Return siblings via shared parents or explicit sibling relationships."""
        from apps.relationships.models import Relationship

        sibling_ids = set()

        # Siblings via shared parents.
        parent_types = {
            Relationship.Type.PARENT_CHILD,
            Relationship.Type.ADOPTIVE_PARENT,
            Relationship.Type.STEP_PARENT,
            Relationship.Type.GUARDIAN,
        }
        parent_ids = Relationship.objects.filter(
            family=self.family,
            to_person=self,
            relationship_type__in=parent_types,
        ).values_list("from_person_id", flat=True)
        if parent_ids:
            sibling_ids.update(
                Relationship.objects.filter(
                    family=self.family,
                    from_person_id__in=parent_ids,
                    relationship_type__in=parent_types,
                )
                .exclude(to_person=self)
                .values_list("to_person_id", flat=True)
            )

        # Siblings via explicit sibling relationships (symmetric).
        sibling_ids.update(
            Relationship.objects.filter(
                family=self.family,
                from_person=self,
                relationship_type=Relationship.Type.SIBLING,
            ).values_list("to_person_id", flat=True)
        )
        sibling_ids.update(
            Relationship.objects.filter(
                family=self.family,
                to_person=self,
                relationship_type=Relationship.Type.SIBLING,
            ).values_list("from_person_id", flat=True)
        )

        return Person.objects.filter(id__in=sibling_ids)

    def to_tree_dict(self, generation=0):
        """Return dict for the radial tree JSON API."""
        from apps.relationships.models import Relationship

        parents = list(self.get_parents())
        partners = list(self.get_partners())
        children = list(self.get_children())
        siblings = list(self.get_siblings())

        # Map to a single father / mother / partner to match the simple radial tree model.
        # Avoid assigning the same single parent as both father and mother.
        father = next(
            (
                p
                for p in sorted(parents, key=lambda p: (p.created_at, p.id))
                if p.gender == Person.Gender.MALE
            ),
            None,
        )
        mother = next(
            (
                p
                for p in sorted(parents, key=lambda p: (p.created_at, p.id))
                if p.gender == Person.Gender.FEMALE
            ),
            None,
        )
        if not father and not mother and parents:
            # Only one parent is known and gender is unclear/unknown/other.
            father = parents[0]

        partner = None
        if partners:
            # Prefer an active spouse, otherwise fall back to the first partner.
            partner_ids = {p.id for p in partners}
            spouse_rel = (
                Relationship.objects.filter(
                    family=self.family,
                    relationship_type=Relationship.Type.SPOUSE,
                )
                .filter(
                    models.Q(from_person=self, to_person_id__in=partner_ids)
                    | models.Q(to_person=self, from_person_id__in=partner_ids)
                )
                .first()
            )
            if spouse_rel:
                spouse_id = (
                    spouse_rel.to_person_id
                    if spouse_rel.from_person_id == self.id
                    else spouse_rel.from_person_id
                )
                partner = next((p for p in partners if p.id == spouse_id), partners[0])
            else:
                partner = partners[0]

        return {
            "id": str(self.id),
            "name": self.full_name,
            "initials": (
                f"{self.first_name[0]}{self.last_name[0]}"
                if self.first_name and self.last_name
                else "??"
            ),
            "gender": self.gender or "unknown",
            "generation": generation,
            "role": "Member",
            "born": self.birth_date.strftime("%d %b %Y") if self.birth_date else None,
            "death_date": self.death_date.strftime("%d %b %Y")
            if self.death_date
            else None,
            "is_living": self.is_living,
            "is_private": self.is_private,
            "visibility": self.visibility,
            "privacy_label": self.get_visibility_display(),
            "life_status": (
                f"Died {self.death_date.strftime('%d %b %Y')}"
                if self.death_date
                else "Deceased"
                if not self.is_living
                else ""
            ),
            "location": self.current_place or self.birth_place or "",
            "occupation": "",
            "avatar_url": self.profile_photo.url if self.profile_photo else None,
            "father_id": str(father.id) if father else None,
            "mother_id": str(mother.id) if mother else None,
            "partner_id": str(partner.id) if partner else None,
            "sibling_ids": [str(s.id) for s in siblings],
            "child_ids": [str(c.id) for c in children],
        }

    def to_public_tree_dict(self, generation=0):
        """Return a privacy-safe payload for public tree visualisation."""
        data = self.to_tree_dict(generation=generation)
        if self.can_be_publicly_identified:
            data.update(
                {
                    "name": self.full_name,
                    "born": self.public_date_label,
                    "location": self.birth_place or self.current_place or "",
                    "biography": self.public_notes or "",
                    "avatar_url": self.profile_photo.url
                    if self.profile_photo
                    else None,
                    "is_public_safe": True,
                    "is_redacted": False,
                }
            )
            return data

        data.update(
            {
                "name": self.public_display_name,
                "initials": "🔒",
                "gender": "unknown",
                "born": None,
                "death_date": None,
                "life_status": "Hidden for privacy" if self.is_living else "Private",
                "location": "Hidden",
                "biography": "",
                "avatar_url": None,
                "is_public_safe": True,
                "is_redacted": True,
                "is_claimed": False,
                "claimed_by_me": False,
                "claimed_by": None,
                "can_edit": False,
                "can_delete": False,
                "can_add_relative": False,
                "can_invite": False,
                "can_set_anchor": False,
            }
        )
        return data
