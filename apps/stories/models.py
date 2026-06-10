from django.conf import settings
from django.db import models


class Story(models.Model):
    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="stories",
    )
    title = models.CharField(max_length=255)
    body = models.TextField()
    people = models.ManyToManyField("people.Person", related_name="stories", blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="stories_authored",
    )
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "stories"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
