from django.contrib import admin

from .models import Memory


@admin.register(Memory)
class MemoryAdmin(admin.ModelAdmin):
    list_display = ["title", "memory_type", "family", "uploaded_by", "created_at"]
    list_filter = ["memory_type", "family"]
    search_fields = ["title", "description"]
    readonly_fields = ["created_at", "updated_at"]
