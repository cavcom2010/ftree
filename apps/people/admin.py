from django.contrib import admin

from .models import Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ["full_name", "family", "gender", "birth_date", "is_living", "is_private"]
    list_filter = ["gender", "is_living", "is_private", "family"]
    search_fields = ["first_name", "middle_name", "last_name", "maiden_name"]
    readonly_fields = ["created_at", "updated_at"]
