from django.contrib import admin

from .models import Activity, Comment, Reaction


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ["actor", "activity_type", "message", "family", "created_at"]
    list_filter = ["activity_type", "family"]
    search_fields = ["message", "actor__username"]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["user", "body_preview", "family", "created_at"]
    list_filter = ["family"]
    search_fields = ["body", "user__username"]

    @admin.display(description="Body")
    def body_preview(self, obj):
        return obj.body[:75]


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = ["user", "reaction_type", "family", "created_at"]
    list_filter = ["reaction_type", "family"]
    search_fields = ["user__username"]
