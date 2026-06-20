from django.contrib import admin

from .models import (
    EmailVerification,
    Family,
    FamilyAuditLog,
    FamilyBranch,
    FamilyConnectionRequest,
    FamilyEditSuggestion,
    FamilyInvitation,
    FamilyInviteLink,
    FamilyMembership,
    FamilyTakedownRequest,
)


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "visibility", "allow_connection_requests", "created_by", "created_at"]
    list_filter = ["visibility", "allow_connection_requests", "allow_public_surname_search"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name", "description", "public_summary", "origin_summary"]
    fieldsets = [
        (None, {"fields": ["name", "slug", "description", "created_by"]}),
        (
            "Public discovery",
            {
                "fields": [
                    "visibility",
                    "public_summary",
                    "origin_summary",
                    "main_surnames",
                    "maiden_surnames",
                    "regions",
                    "allow_connection_requests",
                    "allow_public_surname_search",
                    "show_public_tree_shape",
                    "show_living_private_placeholders",
                ]
            },
        ),
    ]


@admin.register(FamilyMembership)
class FamilyMembershipAdmin(admin.ModelAdmin):
    list_display = ["family", "user", "person", "role", "joined_at"]
    list_filter = ["role", "family"]
    search_fields = ["user__username", "family__name", "person__first_name", "person__last_name"]


@admin.register(FamilyBranch)
class FamilyBranchAdmin(admin.ModelAdmin):
    list_display = ["name", "family", "root_person", "is_public_showcase", "allow_branch_requests"]
    list_filter = ["is_public_showcase", "allow_branch_requests", "family"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name", "family__name", "root_person__first_name", "root_person__last_name"]


@admin.register(FamilyInviteLink)
class FamilyInviteLinkAdmin(admin.ModelAdmin):
    list_display = ["family", "role", "created_by", "use_count", "max_uses", "expires_at", "revoked_at"]
    list_filter = ["role", "revoked_at", "family"]
    search_fields = ["family__name", "note"]
    readonly_fields = ["token", "use_count", "created_at"]


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


@admin.register(FamilyConnectionRequest)
class FamilyConnectionRequestAdmin(admin.ModelAdmin):
    list_display = ["family", "full_name", "user", "status", "match_score", "suggested_person", "created_at"]
    list_filter = ["status", "connection_type", "family"]
    search_fields = ["first_name", "middle_name", "last_name", "maiden_name", "user__username", "family__name"]
    readonly_fields = ["created_at", "updated_at", "reviewed_at"]


@admin.register(FamilyEditSuggestion)
class FamilyEditSuggestionAdmin(admin.ModelAdmin):
    list_display = ["family", "person", "field_name", "status", "user", "created_at"]
    list_filter = ["status", "family", "field_name"]
    search_fields = ["person__first_name", "person__last_name", "field_name", "suggested_value"]


@admin.register(FamilyTakedownRequest)
class FamilyTakedownRequestAdmin(admin.ModelAdmin):
    list_display = ["family", "person", "reporter_email", "reason", "status", "created_at"]
    list_filter = ["status", "family"]
    search_fields = ["reporter_email", "reason", "details", "family__name"]


@admin.register(FamilyAuditLog)
class FamilyAuditLogAdmin(admin.ModelAdmin):
    list_display = ["family", "action", "actor", "object_type", "object_id", "created_at"]
    list_filter = ["action", "family", "created_at"]
    search_fields = ["description", "action", "object_type", "actor__username"]
    readonly_fields = ["created_at"]
