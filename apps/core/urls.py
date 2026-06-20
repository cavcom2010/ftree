from django.urls import path

from apps.families import discovery_views

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", views.home, name="home"),
    path("tree/", discovery_views.tree_entry, name="tree"),
    path("tree/json/", views.tree_json, name="tree_json"),
]
