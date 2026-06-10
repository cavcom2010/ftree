from django.contrib import admin

from .models import FamilyPrompt, PromptAnswer


@admin.register(FamilyPrompt)
class FamilyPromptAdmin(admin.ModelAdmin):
    list_display = ["question", "active_date", "family", "created_at"]
    list_filter = ["family", "active_date"]
    search_fields = ["question"]


@admin.register(PromptAnswer)
class PromptAnswerAdmin(admin.ModelAdmin):
    list_display = ["prompt", "user", "created_at"]
    list_filter = ["prompt__family"]
    search_fields = ["body"]
