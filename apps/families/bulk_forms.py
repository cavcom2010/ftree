from django import forms
from django.forms import formset_factory

from apps.families.forms import PARENT_RELATIONSHIP_CHOICES, PARTNER_RELATIONSHIP_CHOICES
from apps.people.models import Person
from apps.relationships.models import Relationship


BULK_RELATIONSHIP_CHOICES = [
    ("", "Choose relation"),
    ("parent", "Parent"),
    ("child", "Child"),
    ("partner", "Partner"),
    ("sibling", "Sibling"),
]


class BulkRelativeForm(forms.Form):
    relation_type = forms.ChoiceField(
        label="Relationship",
        choices=BULK_RELATIONSHIP_CHOICES,
        required=False,
    )
    first_name = forms.CharField(max_length=100, required=False)
    last_name = forms.CharField(label="Last/current surname", max_length=100, required=False)
    maiden_name = forms.CharField(
        label="Birth/maiden surname",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Optional"}),
    )
    gender = forms.ChoiceField(
        required=False,
        choices=Person.Gender.choices,
        initial=Person.Gender.UNKNOWN,
    )
    birth_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    is_living = forms.TypedChoiceField(
        label="Life status",
        choices=[
            (True, "Living"),
            (False, "Deceased"),
        ],
        coerce=lambda value: value in {True, "True", "true", "1", 1},
        initial=True,
        required=False,
        empty_value=True,
    )
    death_date = forms.DateField(
        label="Death date",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    parent_relationship_type = forms.ChoiceField(
        label="Parent type",
        choices=PARENT_RELATIONSHIP_CHOICES,
        required=False,
        initial=Relationship.Type.PARENT_CHILD,
        help_text="Only used for parent rows.",
    )
    partner_relationship_type = forms.ChoiceField(
        label="Partner type",
        choices=PARTNER_RELATIONSHIP_CHOICES,
        required=False,
        initial=Relationship.Type.SPOUSE,
        help_text="Only used for partner rows.",
    )

    def has_relative_data(self):
        if not hasattr(self, "cleaned_data") or self.cleaned_data.get("DELETE"):
            return False
        meaningful_fields = [
            "relation_type",
            "first_name",
            "last_name",
            "maiden_name",
            "birth_date",
            "death_date",
        ]
        return any(self.cleaned_data.get(field_name) for field_name in meaningful_fields)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("DELETE") or not self.has_relative_data():
            return cleaned_data

        relation_type = cleaned_data.get("relation_type")
        first_name = (cleaned_data.get("first_name") or "").strip()
        last_name = (cleaned_data.get("last_name") or "").strip()
        is_living = cleaned_data.get("is_living")
        death_date = cleaned_data.get("death_date")

        if relation_type not in {"parent", "child", "partner", "sibling"}:
            self.add_error("relation_type", "Choose how this person is related.")

        if not first_name:
            self.add_error("first_name", "Enter a first name.")

        if not last_name:
            self.add_error("last_name", "Enter a surname.")

        if is_living and death_date:
            self.add_error("death_date", "Mark this relative as deceased before adding a death date.")

        return cleaned_data


BulkRelativeFormSet = formset_factory(
    BulkRelativeForm,
    extra=10,
    can_delete=True,
)
