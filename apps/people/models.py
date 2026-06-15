import uuid
from pathlib import Path

from django.conf import settings
from django.db import models


def person_profile_photo_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"people/profile-photos/{uuid.uuid4()}{extension}"


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
        upload_to=person_profile_photo_upload_path,
        null=True,
        blank=True,
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
