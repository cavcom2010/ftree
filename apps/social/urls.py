from django.urls import path

from . import views

urlpatterns = [
    path("feed/", views.family_feed, name="family_feed"),
    path(
        "react/<str:content_type>/<int:object_id>/<str:reaction_type>/",
        views.toggle_reaction,
        name="toggle_reaction",
    ),
    path(
        "comment/<str:content_type>/<int:object_id>/",
        views.add_comment,
        name="add_comment",
    ),
]
