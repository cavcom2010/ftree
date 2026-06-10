from django.contrib import admin

from .models import Relationship


@admin.register(Relationship)
class RelationshipAdmin(admin.ModelAdmin):
    list_display = ["from_person", "to_person", "relationship_type", "family", "created_at"]
    list_filter = ["relationship_type", "family"]
    search_fields = ["from_person__first_name", "from_person__last_name", "to_person__first_name", "to_person__last_name"]
