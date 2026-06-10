from django.urls import path

from . import views

urlpatterns = [
    path("prompts/current/", views.current_prompt, name="current_prompt"),
    path("prompts/<int:prompt_id>/answer/", views.answer_prompt, name="answer_prompt"),
]
