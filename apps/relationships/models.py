from django.core.exceptions import ValidationError
from django.db import models


class Relationship(models.Model):
    class Type(models.TextChoices):
        PARENT_CHILD = "parent_child", "Parent → Child"
        SPOUSE = "spouse", "Spouse"
        SIBLING = "sibling", "Sibling"
        ADOPTIVE_PARENT = "adoptive_parent", "Adoptive Parent"
        GUARDIAN = "guardian", "Guardian"

    PARENT_LIKE_TYPES = (
        Type.PARENT_CHILD,
        Type.ADOPTIVE_PARENT,
        Type.GUARDIAN,
    )
    SYMMETRIC_TYPES = (
        Type.SPOUSE,
        Type.SIBLING,
    )
    MAX_PARENT_LIKE_RELATIONSHIPS = 4

    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="relationships",
    )
    from_person = models.ForeignKey(
        "people.Person",
        on_delete=models.CASCADE,
        related_name="relationships_from",
    )
    to_person = models.ForeignKey(
        "people.Person",
        on_delete=models.CASCADE,
        related_name="relationships_to",
    )
    relationship_type = models.CharField(
        max_length=30, choices=Type.choices, default=Type.PARENT_CHILD
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["family", "from_person"]),
            models.Index(fields=["family", "to_person"]),
            models.Index(fields=["relationship_type"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "from_person", "to_person", "relationship_type"],
                name="unique_family_relationship_edge",
            ),
        ]

    def __str__(self):
        return (
            f"{self.from_person} → {self.to_person} "
            f"({self.get_relationship_type_display()})"
        )

    def clean(self):
        errors = {}

        if self.from_person_id and self.to_person_id and self.from_person_id == self.to_person_id:
            errors["to_person"] = "A relationship cannot point to the same person."

        if self.family_id and self.from_person_id and self.from_person.family_id != self.family_id:
            errors["from_person"] = "Source person must belong to this family."

        if self.family_id and self.to_person_id and self.to_person.family_id != self.family_id:
            errors["to_person"] = "Target person must belong to this family."

        if not errors and self.from_person_id and self.to_person_id and self.relationship_type:
            errors.update(self._rule_errors())

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def _rule_errors(self):
        if self.relationship_type in self.PARENT_LIKE_TYPES:
            return self._parent_like_errors()
        if self.relationship_type in self.SYMMETRIC_TYPES:
            return self._reverse_duplicate_errors()
        return {}

    def _parent_like_errors(self):
        errors = {}
        existing_parent_links = (
            Relationship.objects.filter(
                family_id=self.family_id,
                to_person_id=self.to_person_id,
                relationship_type__in=self.PARENT_LIKE_TYPES,
            )
            .exclude(pk=self.pk)
            .count()
        )

        if existing_parent_links >= self.MAX_PARENT_LIKE_RELATIONSHIPS:
            errors["to_person"] = "This person already has the maximum number of parent/guardian links."

        if self._would_create_cycle():
            errors["from_person"] = "This link would create a circular ancestry loop."

        return errors

    def _reverse_duplicate_errors(self):
        reverse_exists = (
            Relationship.objects.filter(
                family_id=self.family_id,
                from_person_id=self.to_person_id,
                to_person_id=self.from_person_id,
                relationship_type=self.relationship_type,
            )
            .exclude(pk=self.pk)
            .exists()
        )
        return {"to_person": "This reverse relationship already exists."} if reverse_exists else {}

    def _would_create_cycle(self):
        descendants_to_visit = [self.to_person_id]
        visited = set()

        while descendants_to_visit:
            person_id = descendants_to_visit.pop()
            if person_id == self.from_person_id:
                return True
            if person_id in visited:
                continue

            visited.add(person_id)
            descendants_to_visit.extend(
                Relationship.objects.filter(
                    family_id=self.family_id,
                    from_person_id=person_id,
                    relationship_type__in=self.PARENT_LIKE_TYPES,
                ).values_list("to_person_id", flat=True)
            )

        return False
