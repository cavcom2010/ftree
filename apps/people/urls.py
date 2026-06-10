from django.urls import path

from . import views

urlpatterns = [
    path(
        "people/<int:person_id>/drawer/",
        views.person_drawer,
        name="person_drawer",
    ),
    path(
        "people/<int:person_id>/descendants/",
        views.person_descendants,
        name="person_descendants",
    ),
]
