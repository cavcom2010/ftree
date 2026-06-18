from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", views.home, name="home"),
    path("tree/", views.tree, name="tree"),
    path("tree/json/", views.tree_json, name="tree_json"),
]
