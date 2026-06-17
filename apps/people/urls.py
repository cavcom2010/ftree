from django.urls import path

from . import views

urlpatterns = [
    path(
        "people/<int:person_id>/drawer/",
        views.person_drawer,
        name="person_drawer",
    ),
    path(
        "people/<int:person_id>/edit-name/",
        views.person_edit_name,
        name="person_edit_name",
    ),
    path(
        "people/<int:person_id>/descendants/",
        views.person_descendants,
        name="person_descendants",
    ),
    path(
        "people/create/",
        views.person_create,
        name="person_create",
    ),
    path(
        "people/<int:person_id>/delete/",
        views.person_delete,
        name="person_delete",
    ),
]
