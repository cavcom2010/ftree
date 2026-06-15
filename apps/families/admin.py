from django.contrib import admin

from .models import EmailVerification, Family, FamilyInvitation, FamilyMembership


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


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = ["email", "user", "created_at", "expires_at", "verified_at"]
    list_filter = ["verified_at", "expires_at"]
    search_fields = ["email", "user__username", "user__email"]
    readonly_fields = ["token", "created_at", "verified_at"]


@admin.register(FamilyInvitation)
class FamilyInvitationAdmin(admin.ModelAdmin):
    list_display = ["family", "person", "invitee_label", "status", "role", "inviter", "sent_at"]
    list_filter = ["status", "role", "family"]
    search_fields = [
        "invitee_email",
        "invitee_user__username",
        "person__first_name",
        "person__last_name",
        "family__name",
    ]
    readonly_fields = ["token", "sent_at", "responded_at"]
