from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.families.models import FamilyMembership
from apps.people.models import Person
from apps.relationships.models import Relationship


PARENT_RELATIONSHIP_CHOICES = [
    (Relationship.Type.PARENT_CHILD, "Parent"),
    (Relationship.Type.ADOPTIVE_PARENT, "Adoptive parent"),
    (Relationship.Type.STEP_PARENT, "Step-parent"),
    (Relationship.Type.GUARDIAN, "Guardian"),
]

PARTNER_RELATIONSHIP_CHOICES = [
    (Relationship.Type.SPOUSE, "Spouse"),
    (Relationship.Type.PARTNER, "Partner"),
    (Relationship.Type.EX_PARTNER, "Ex-partner"),
]


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
    parent_relationship_type = forms.ChoiceField(
        label="Parent type",
        choices=PARENT_RELATIONSHIP_CHOICES,
        required=False,
        initial=Relationship.Type.PARENT_CHILD,
    )
    partner_relationship_type = forms.ChoiceField(
        label="Partner type",
        choices=PARTNER_RELATIONSHIP_CHOICES,
        required=False,
        initial=Relationship.Type.SPOUSE,
    )
    other_parent = forms.ModelChoiceField(
        label="Other parent",
        queryset=Person.objects.none(),
        required=False,
        empty_label="No other parent selected",
    )
    shared_parents = forms.ModelMultipleChoiceField(
        label="Shared parents",
        queryset=Person.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    partner_shared_children = forms.ModelMultipleChoiceField(
        label="Children you share with this partner",
        queryset=Person.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select existing children who should also be connected to this partner.",
    )
    parent_shared_children = forms.ModelMultipleChoiceField(
        label="Existing siblings who are also this parent's children",
        queryset=Person.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select your existing siblings who should also be connected to this parent.",
    )

    def __init__(self, *args, family=None, anchor_person=None, relation_type="", **kwargs):
        super().__init__(*args, **kwargs)
        self.family = family
        self.anchor_person = anchor_person
        self.relation_type = relation_type
        if family and anchor_person:
            self.fields["other_parent"].queryset = _partners_for_person(family, anchor_person)
            shared_parent_queryset = _parents_for_person(family, anchor_person)
            self.fields["shared_parents"].queryset = shared_parent_queryset
            self.fields["partner_shared_children"].queryset = _children_for_person(family, anchor_person)
            self.fields["parent_shared_children"].queryset = _siblings_for_person(family, anchor_person)
            if not self.is_bound:
                self.initial["shared_parents"] = list(shared_parent_queryset.values_list("id", flat=True))


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, max_length=254)
    website = forms.CharField(
        required=False,
        widget=forms.HiddenInput,
        help_text="Leave this field blank.",
    )

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with that username already exists.")
        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email address already exists.")
        return email

    def clean_website(self):
        value = self.cleaned_data.get("website")
        if value:
            raise forms.ValidationError("Invalid signup submission.")
        return value


def _parent_types():
    return [
        Relationship.Type.PARENT_CHILD,
        Relationship.Type.ADOPTIVE_PARENT,
        Relationship.Type.STEP_PARENT,
        Relationship.Type.GUARDIAN,
    ]


def _partners_for_person(family, person):
    partner_types = [
        Relationship.Type.SPOUSE,
        Relationship.Type.PARTNER,
        Relationship.Type.EX_PARTNER,
    ]
    relationships = Relationship.objects.filter(
        Q(from_person=person) | Q(to_person=person),
        family=family,
        relationship_type__in=partner_types,
    )
    partner_ids = []
    for relationship in relationships:
        partner_ids.append(
            relationship.to_person_id
            if relationship.from_person_id == person.id
            else relationship.from_person_id
        )
    return Person.objects.filter(family=family, id__in=partner_ids).order_by("first_name", "last_name")


def _parents_for_person(family, person):
    parent_ids = Relationship.objects.filter(
        family=family,
        to_person=person,
        relationship_type__in=_parent_types(),
    ).values_list("from_person_id", flat=True)
    return Person.objects.filter(family=family, id__in=parent_ids).order_by("first_name", "last_name")


def _children_for_person(family, person):
    child_ids = Relationship.objects.filter(
        family=family,
        from_person=person,
        relationship_type__in=_parent_types(),
    ).values_list("to_person_id", flat=True)
    return Person.objects.filter(family=family, id__in=child_ids).order_by("birth_date", "first_name", "last_name")


def _siblings_for_person(family, person):
    sibling_ids = set()

    sibling_relationships = Relationship.objects.filter(
        family=family,
        relationship_type=Relationship.Type.SIBLING,
    ).filter(Q(from_person=person) | Q(to_person=person))
    for relationship in sibling_relationships:
        sibling_ids.add(
            relationship.to_person_id
            if relationship.from_person_id == person.id
            else relationship.from_person_id
        )

    parent_ids = Relationship.objects.filter(
        family=family,
        to_person=person,
        relationship_type__in=_parent_types(),
    ).values_list("from_person_id", flat=True)
    sibling_ids.update(
        Relationship.objects.filter(
            family=family,
            from_person_id__in=parent_ids,
            relationship_type__in=_parent_types(),
        )
        .exclude(to_person=person)
        .values_list("to_person_id", flat=True)
    )

    return Person.objects.filter(family=family, id__in=sibling_ids).order_by("birth_date", "first_name", "last_name")
