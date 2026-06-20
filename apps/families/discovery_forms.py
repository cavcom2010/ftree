from django import forms

from apps.families.models import FamilyConnectionRequest, FamilyTakedownRequest


class StartTreeIdentityForm(forms.Form):
    first_name = forms.CharField(max_length=100)
    middle_name = forms.CharField(max_length=100, required=False)
    last_name = forms.CharField(label="Surname", max_length=100)
    maiden_name = forms.CharField(label="Previous / birth surname", max_length=100, required=False)
    birth_date = forms.DateField(label="Date of birth", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    parent_clue = forms.CharField(label="Known parent name", max_length=255, required=False)
    grandparent_clue = forms.CharField(label="Known grandparent name", max_length=255, required=False)
    region_clue = forms.CharField(label="Country, town, village, or region", max_length=255, required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and getattr(user, "is_authenticated", False) and not self.is_bound:
            self.initial["first_name"] = user.first_name or ""
            self.initial["last_name"] = user.last_name or ""
            if not self.initial["first_name"] and user.get_full_name():
                parts = user.get_full_name().split()
                self.initial["first_name"] = parts[0]
                self.initial["last_name"] = " ".join(parts[1:])
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "discovery-input")


class ConnectionRequestForm(StartTreeIdentityForm):
    connection_type = forms.ChoiceField(
        choices=FamilyConnectionRequest.ConnectionType.choices,
        initial=FamilyConnectionRequest.ConnectionType.IN_FAMILY,
    )
    requester_message = forms.CharField(
        label="Message to the tree owner",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Explain how you believe you are connected."}),
    )


class TakedownRequestForm(forms.ModelForm):
    class Meta:
        model = FamilyTakedownRequest
        fields = ["reporter_email", "reason", "details"]
        widgets = {"details": forms.Textarea(attrs={"rows": 5})}
