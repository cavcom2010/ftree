from django import forms
from django.core.exceptions import ValidationError

from apps.people.models import Person


class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = [
            "first_name",
            "last_name",
            "middle_name",
            "maiden_name",
            "profile_photo",
            "gender",
            "birth_date",
            "death_date",
            "birth_place",
            "current_place",
            "biography",
            "is_private",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "death_date": forms.DateInput(attrs={"type": "date"}),
            "biography": forms.Textarea(attrs={"rows": 3}),
            "profile_photo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }


class PersonNameForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ["first_name", "middle_name", "last_name", "maiden_name"]
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "middle_name": forms.TextInput(attrs={"autocomplete": "additional-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "maiden_name": forms.TextInput(attrs={"autocomplete": "off"}),
        }


class PersonEditForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = [
            "first_name",
            "last_name",
            "middle_name",
            "maiden_name",
            "gender",
            "birth_date",
            "death_date",
            "birth_place",
            "current_place",
            "biography",
            "is_private",
            "is_living",
            "visibility",
            "public_notes",
            "profile_photo",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "death_date": forms.DateInput(attrs={"type": "date"}),
            "biography": forms.Textarea(attrs={"rows": 3}),
            "public_notes": forms.Textarea(attrs={"rows": 2}),
            "profile_photo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        is_living = cleaned_data.get("is_living")
        death_date = cleaned_data.get("death_date")
        if is_living and death_date:
            raise ValidationError(
                "Mark this person as deceased before adding a death date."
            )
        return cleaned_data
