from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.db.models import Case, IntegerField, Q, When

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
    (Relationship.Type.CO_PARENT, "Co-parent"),
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
    LIVING_CHOICES = [
        (True, "Living"),
        (False, "Deceased"),
    ]

    invitee = forms.CharField(
        label="Invite username or email",
        max_length=254,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Optional username or email"}),
        help_text="Optional. Leave blank to add a family-tree profile without inviting an account yet.",
    )
    existing_person = forms.ModelChoiceField(
        label="Connect existing person",
        queryset=Person.objects.none(),
        required=False,
        empty_label="Create a new profile",
        help_text="Suggested co-parents appear first. Leave blank to create a new profile.",
    )
    first_name = forms.CharField(max_length=100, required=False)
    last_name = forms.CharField(label="Last/current surname", max_length=100, required=False)
    maiden_name = forms.CharField(
        label="Birth/maiden surname",
        max_length=100,
        required=False,
        help_text="Optional. Useful for married female relatives or anyone whose birth surname differs.",
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
        choices=LIVING_CHOICES,
        coerce=lambda value: value in {True, "True", "true", "1", 1},
        initial=True,
        required=False,
        empty_value=True,
        widget=forms.RadioSelect,
    )
    death_date = forms.DateField(
        label="Death date",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Optional. Leave blank if the exact date is unknown.",
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
        initial=Relationship.Type.CO_PARENT,
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
            self.fields["existing_person"].queryset = _existing_partner_candidates(family, anchor_person)
            shared_parent_queryset = _parents_for_person(family, anchor_person)
            self.fields["shared_parents"].queryset = shared_parent_queryset
            self.fields["partner_shared_children"].queryset = _children_for_person(family, anchor_person)
            self.fields["parent_shared_children"].queryset = _siblings_for_person(family, anchor_person)
            if not self.is_bound and relation_type in {"partner", "spouse"}:
                self.initial["partner_relationship_type"] = Relationship.Type.CO_PARENT
            if not self.is_bound:
                self.initial["shared_parents"] = list(shared_parent_queryset.values_list("id", flat=True))

    def clean(self):
        cleaned_data = super().clean()
        existing_person = cleaned_data.get("existing_person")
        first_name = (cleaned_data.get("first_name") or "").strip()
        last_name = (cleaned_data.get("last_name") or "").strip()
        is_living = cleaned_data.get("is_living")
        death_date = cleaned_data.get("death_date")
        invitee = (cleaned_data.get("invitee") or "").strip()

        if existing_person and self.relation_type not in {"partner", "spouse"}:
            self.add_error("existing_person", "Existing-person connection is available for partners and co-parents.")

        if not existing_person and is_living and death_date:
            self.add_error("death_date", "Mark this relative as deceased before adding a death date.")

        effective_is_living = existing_person.is_living if existing_person else is_living
        if invitee and effective_is_living is False:
            self.add_error("invitee", "Deceased relatives cannot be invited to claim an account.")

        if not existing_person:
            if not first_name:
                self.add_error("first_name", "Enter a first name or choose an existing person.")
            if not last_name:
                self.add_error("last_name", "Enter a surname or choose an existing person.")

        return cleaned_data


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


def _partner_types():
    return [
        Relationship.Type.SPOUSE,
        Relationship.Type.PARTNER,
        Relationship.Type.EX_PARTNER,
        Relationship.Type.CO_PARENT,
    ]


def _partners_for_person(family, person):
    relationships = Relationship.objects.filter(
        Q(from_person=person) | Q(to_person=person),
        family=family,
        relationship_type__in=_partner_types(),
    )
    partner_ids = []
    for relationship in relationships:
        partner_ids.append(
            relationship.to_person_id
            if relationship.from_person_id == person.id
            else relationship.from_person_id
        )
    return Person.objects.filter(family=family, id__in=partner_ids).order_by("first_name", "last_name")


def _existing_partner_candidates(family, person):
    likely_ids = _co_parent_candidate_ids(family, person)
    excluded_ids = {person.id}
    excluded_ids.update(_direct_relative_ids(family, person))
    excluded_ids.update(_partners_for_person(family, person).values_list("id", flat=True))

    likely_order = Case(
        *[When(id=person_id, then=0) for person_id in likely_ids],
        default=1,
        output_field=IntegerField(),
    )
    return (
        Person.objects.filter(family=family)
        .exclude(id__in=excluded_ids)
        .annotate(connection_rank=likely_order)
        .order_by("connection_rank", "birth_date", "first_name", "last_name", "id")
    )


def _co_parent_candidate_ids(family, person):
    child_ids = Relationship.objects.filter(
        family=family,
        from_person=person,
        relationship_type__in=_parent_types(),
    ).values_list("to_person_id", flat=True)
    return set(
        Relationship.objects.filter(
            family=family,
            to_person_id__in=child_ids,
            relationship_type__in=_parent_types(),
        )
        .exclude(from_person=person)
        .values_list("from_person_id", flat=True)
    )


def _direct_relative_ids(family, person):
    direct_ids = set()
    direct_ids.update(
        Relationship.objects.filter(
            family=family,
            to_person=person,
            relationship_type__in=_parent_types(),
        ).values_list("from_person_id", flat=True)
    )
    direct_ids.update(
        Relationship.objects.filter(
            family=family,
            from_person=person,
            relationship_type__in=_parent_types(),
        ).values_list("to_person_id", flat=True)
    )
    direct_ids.update(_siblings_for_person(family, person).values_list("id", flat=True))
    return direct_ids


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
