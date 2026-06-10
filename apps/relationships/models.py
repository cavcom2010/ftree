from django.db import models


class Relationship(models.Model):
    class Type(models.TextChoices):
        PARENT_CHILD = "parent_child", "Parent → Child"
        SPOUSE = "spouse", "Spouse"
        SIBLING = "sibling", "Sibling"
        ADOPTIVE_PARENT = "adoptive_parent", "Adoptive Parent"
        GUARDIAN = "guardian", "Guardian"

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

    def __str__(self):
        return (
            f"{self.from_person} → {self.to_person} "
            f"({self.get_relationship_type_display()})"
        )
