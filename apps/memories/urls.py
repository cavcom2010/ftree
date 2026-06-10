from django.urls import path

from . import views

urlpatterns = [
    path("memories/", views.memory_list, name="memory_list"),
]
