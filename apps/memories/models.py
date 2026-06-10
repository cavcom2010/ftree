from django.conf import settings
from django.db import models


class Memory(models.Model):
    class Type(models.TextChoices):
        PHOTO = "photo", "Photo"
        VIDEO = "video", "Video"
        AUDIO = "audio", "Audio"
        DOCUMENT = "document", "Document"

    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="memories",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    memory_type = models.CharField(max_length=20, choices=Type.choices)
    file = models.FileField(upload_to="memories/%Y/%m/")
    people = models.ManyToManyField("people.Person", related_name="memories", blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="memories_uploaded",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "memories"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
