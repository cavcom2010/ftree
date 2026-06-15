from django import forms

from apps.people.models import Person


class PersonForm(forms.ModelForm):
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
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "death_date": forms.DateInput(attrs={"type": "date"}),
            "biography": forms.Textarea(attrs={"rows": 3}),
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
