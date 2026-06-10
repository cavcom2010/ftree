from django.conf import settings
from django.db import models


class FamilyPrompt(models.Model):
    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="prompts",
    )
    question = models.CharField(max_length=500)
    active_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-active_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "active_date"],
                name="unique_family_prompt_date",
            )
        ]

    def __str__(self):
        return f"{self.active_date}: {self.question[:60]}"


class PromptAnswer(models.Model):
    prompt = models.ForeignKey(
        FamilyPrompt,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="prompt_answers",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user}: {self.body[:50]}"
