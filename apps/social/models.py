from django.conf import settings
from django.db import models


class Activity(models.Model):
    class Type(models.TextChoices):
        PERSON_ADDED = "person_added", "Person Added"
        RELATIONSHIP_ADDED = "relationship_added", "Relationship Added"
        MEMORY_ADDED = "memory_added", "Memory Added"
        STORY_ADDED = "story_added", "Story Added"
        COMMENT_ADDED = "comment_added", "Comment Added"
        ACHIEVEMENT_EARNED = "achievement_earned", "Achievement Earned"

    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="activities",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="activities",
    )
    activity_type = models.CharField(max_length=30, choices=Type.choices)
    message = models.CharField(max_length=500)
    person = models.ForeignKey(
        "people.Person",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities",
    )
    memory = models.ForeignKey(
        "memories.Memory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities",
    )
    story = models.ForeignKey(
        "stories.Story",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "activities"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.actor}: {self.message}"


class Comment(models.Model):
    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="comments",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="comments",
    )
    body = models.TextField()
    story = models.ForeignKey(
        "stories.Story",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comments",
    )
    memory = models.ForeignKey(
        "memories.Memory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user}: {self.body[:50]}"


class Reaction(models.Model):
    class Type(models.TextChoices):
        LOVE = "love", "Love"
        RESPECT = "respect", "Respect"
        FUNNY = "funny", "Funny"
        MISS_THEM = "miss_them", "Miss Them"
        THANKS = "thanks", "Thanks"

    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="reactions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="reactions",
    )
    reaction_type = models.CharField(max_length=20, choices=Type.choices)
    story = models.ForeignKey(
        "stories.Story",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reactions",
    )
    memory = models.ForeignKey(
        "memories.Memory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reactions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user}: {self.get_reaction_type_display()}"
