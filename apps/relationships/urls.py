from django.urls import path

from . import views

urlpatterns = [
    path(
        "people/<int:person_id>/add-relative/<str:relation_type>/",
        views.add_relative,
        name="add_relative",
    ),
    path(
        "relationships/finder/",
        views.relationship_finder,
        name="relationship_finder",
    ),
]
