from django.conf import settings
from django.db import models


class Person(models.Model):
    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"
        UNKNOWN = "unknown", "Unknown"

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
        upload_to="people/photos/", null=True, blank=True
    )
    biography = models.TextField(blank=True, default="")
    is_living = models.BooleanField(default=True)
    is_private = models.BooleanField(default=False)
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

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        return " ".join(parts)

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
            (p for p in sorted(parents, key=lambda p: (p.created_at, p.id))
             if p.gender == Person.Gender.MALE), None
        )
        mother = next(
            (p for p in sorted(parents, key=lambda p: (p.created_at, p.id))
             if p.gender == Person.Gender.FEMALE), None
        )
        if not father and not mother and parents:
            # Only one parent is known and gender is unclear/unknown/other.
            father = parents[0]

        partner = None
        if partners:
            # Prefer an active spouse, otherwise fall back to the first partner.
            partner_ids = {p.id for p in partners}
            spouse_rel = Relationship.objects.filter(
                family=self.family,
                relationship_type=Relationship.Type.SPOUSE,
            ).filter(
                models.Q(from_person=self, to_person_id__in=partner_ids)
                | models.Q(to_person=self, from_person_id__in=partner_ids)
            ).first()
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
            "death_date": self.death_date.strftime("%d %b %Y") if self.death_date else None,
            "is_living": self.is_living,
            "life_status": (
                f"Died {self.death_date.strftime('%d %b %Y')}"
                if self.death_date
                else "Deceased" if not self.is_living else ""
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
