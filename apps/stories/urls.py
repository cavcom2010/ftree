from django.urls import path

from . import views

urlpatterns = [
    path("stories/", views.story_list, name="story_list"),
    path("stories/create/", views.story_create, name="story_create"),
]
