from django.contrib import admin

from .models import Story


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ["title", "family", "author", "is_featured", "created_at"]
    list_filter = ["is_featured", "family"]
    search_fields = ["title", "body"]
    readonly_fields = ["created_at", "updated_at"]
