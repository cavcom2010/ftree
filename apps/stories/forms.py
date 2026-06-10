from django import forms

from apps.stories.models import Story


class StoryForm(forms.ModelForm):
    class Meta:
        model = Story
        fields = ["title", "body", "is_featured"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 5}),
        }
