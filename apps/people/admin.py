from django.contrib import admin
from django.utils.html import format_html

from .models import Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = [
        "full_name",
        "family",
        "gender",
        "birth_date",
        "has_profile_photo",
        "is_living",
        "is_private",
        "visibility",
    ]
    list_filter = ["gender", "is_living", "is_private", "visibility", "family"]
    search_fields = ["first_name", "middle_name", "last_name", "maiden_name"]
    readonly_fields = ["profile_photo_preview", "created_at", "updated_at", "public_display_name", "public_date_label"]
    fields = [
        "family",
        "first_name",
        "middle_name",
        "last_name",
        "maiden_name",
        "gender",
        "birth_date",
        "death_date",
        "birth_place",
        "current_place",
        "profile_photo",
        "profile_photo_preview",
        "biography",
        "is_living",
        "is_private",
        "visibility",
        "public_display_name",
        "public_date_label",
        "public_notes",
        "created_by",
        "created_at",
        "updated_at",
    ]

    @admin.display(boolean=True, description="Photo")
    def has_profile_photo(self, obj):
        return bool(obj.profile_photo)

    @admin.display(description="Profile photo preview")
    def profile_photo_preview(self, obj):
        if not obj.profile_photo:
            return "No profile photo"
        try:
            url = obj.profile_photo.url
        except Exception:
            return "Profile photo unavailable"
        return format_html(
            '<img src="{}" alt="{}" style="width:72px;height:72px;border-radius:50%;'
            'object-fit:cover;border:3px solid #d946ef;box-shadow:0 6px 18px rgba(168,85,247,.22);">',
            url,
            obj.full_name,
        )
