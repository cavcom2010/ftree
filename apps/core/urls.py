from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("tree/", views.tree, name="tree"),
    path("health/", views.health, name="health"),
]
