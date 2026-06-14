from django.contrib import admin

from .models import Family, FamilyMembership


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "created_by", "created_at"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name", "description"]


@admin.register(FamilyMembership)
class FamilyMembershipAdmin(admin.ModelAdmin):
    list_display = ["family", "user", "person", "role", "joined_at"]
    list_filter = ["role", "family"]
    search_fields = ["user__username", "family__name", "person__first_name", "person__last_name"]
