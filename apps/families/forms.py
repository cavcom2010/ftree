from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from apps.families.models import FamilyMembership
from apps.people.models import Person


class InvitePersonForm(forms.Form):
    invitee = forms.CharField(
        label="Username or email",
        max_length=254,
        widget=forms.TextInput(attrs={"placeholder": "relative@example.com or username"}),
    )
    role = forms.ChoiceField(
        choices=[
            (FamilyMembership.Role.MEMBER, "Member"),
            (FamilyMembership.Role.VIEWER, "Viewer"),
        ],
        initial=FamilyMembership.Role.MEMBER,
    )
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Add a personal note"}),
    )


class InviteRelativeForm(InvitePersonForm):
    invitee = forms.CharField(
        label="Invite username or email",
        max_length=254,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Optional username or email"}),
        help_text="Optional. Leave blank to add a family-tree profile without inviting an account yet.",
    )
    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100)
    gender = forms.ChoiceField(
        required=False,
        choices=Person.Gender.choices,
        initial=Person.Gender.UNKNOWN,
    )
    birth_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")
