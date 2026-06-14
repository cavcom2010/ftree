from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
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

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
