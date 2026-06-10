from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("", include("apps.people.urls")),
    path("", include("apps.relationships.urls")),
    path("", include("apps.social.urls")),
    path("", include("apps.stories.urls")),
    path("", include("apps.memories.urls")),
    path("", include("apps.prompts.urls")),
]
