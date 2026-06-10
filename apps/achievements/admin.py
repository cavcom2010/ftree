from django.contrib import admin

from .models import Achievement, UserAchievement


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "icon"]
    search_fields = ["name", "description"]


@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ["user", "achievement", "family", "earned_at"]
    list_filter = ["achievement", "family"]
    search_fields = ["user__username"]
