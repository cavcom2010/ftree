from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.families.forms import InvitePersonForm, InviteRelativeForm, SignupForm
from apps.families.models import Family, FamilyInvitation
from apps.families.services import (
    accept_invitation,
    create_invitation,
    create_relative_with_optional_invite,
    current_family_for_user,
    decline_invitation,
    ignore_invitation,
)
from apps.people.models import Person


RELATION_LABELS = {
    "parent": "Parent",
    "child": "Child",
    "partner": "Partner",
    "spouse": "Partner",
    "sibling": "Sibling",
}


@login_required
def invite_person(request, person_id):
    family = _current_family(request)
    person = get_object_or_404(Person, id=person_id, family=family)

    if request.method == "POST":
        form = InvitePersonForm(request.POST)
        if form.is_valid():
            try:
                invitation = create_invitation(
                    family=family,
                    inviter=request.user,
                    person=person,
                    invitee_identifier=form.cleaned_data["invitee"],
                    role=form.cleaned_data["role"],
                    message=form.cleaned_data["message"],
                )
            except (ValidationError, PermissionDenied) as exc:
                _add_form_error(form, exc)
            else:
                return _render_invite_success(request, invitation)
    else:
        form = InvitePersonForm()

    return render(
        request,
        "families/partials/invite_person_sheet.html",
        {
            "form": form,
            "family": family,
            "person": person,
            "title": f"Invite {person.full_name}",
            "submit_label": "Send invite",
        },
    )


@login_required
def invite_relative(request, person_id, relation_type):
    family = _current_family(request)
    anchor_person = get_object_or_404(Person, id=person_id, family=family)
    relation_type = relation_type if relation_type in RELATION_LABELS else "child"
    form_kwargs = {
        "family": family,
        "anchor_person": anchor_person,
        "relation_type": relation_type,
    }

    if request.method == "POST":
        form = InviteRelativeForm(request.POST, **form_kwargs)
        if form.is_valid():
            try:
                person, invitation = create_relative_with_optional_invite(
                    family=family,
                    inviter=request.user,
                    anchor_person=anchor_person,
                    relation_type=relation_type,
                    person_data={
                        "first_name": form.cleaned_data["first_name"],
                        "last_name": form.cleaned_data["last_name"],
                        "gender": form.cleaned_data["gender"],
                        "birth_date": form.cleaned_data["birth_date"],
                    },
                    invitee_identifier=form.cleaned_data["invitee"],
                    role=form.cleaned_data["role"],
                    message=form.cleaned_data["message"],
                    parent_relationship_type=form.cleaned_data["parent_relationship_type"],
                    partner_relationship_type=form.cleaned_data["partner_relationship_type"],
                    other_parent=form.cleaned_data["other_parent"],
                    shared_parents=form.cleaned_data["shared_parents"],
                )
            except (ValidationError, PermissionDenied) as exc:
                _add_form_error(form, exc)
            else:
                return _render_relative_success(request, person, invitation)
    else:
        form = InviteRelativeForm(**form_kwargs)

    return render(
        request,
        "families/partials/invite_relative_sheet.html",
        {
            "form": form,
            "family": family,
            "anchor_person": anchor_person,
            "relation_type": relation_type,
            "relation_label": RELATION_LABELS[relation_type],
            "submit_label": f"Add {RELATION_LABELS[relation_type].lower()}",
        },
    )


def invitation_detail(request, token):
    invitation = get_object_or_404(
        FamilyInvitation.objects.select_related("family", "person", "inviter", "invitee_user"),
        token=token,
    )
    return render(
        request,
        "families/invitation_detail.html",
        {
            "invitation": invitation,
            "accept_url": reverse("family_invitation_accept", args=[invitation.token]),
            "decline_url": reverse("family_invitation_decline", args=[invitation.token]),
            "ignore_url": reverse("family_invitation_ignore", args=[invitation.token]),
        },
    )


@login_required
def invitation_accept(request, token):
    if request.method != "POST":
        return HttpResponseBadRequest("Use POST to accept an invitation.")
    invitation = get_object_or_404(FamilyInvitation, token=token)
    try:
        accept_invitation(invitation, request.user)
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, str(exc))
        return redirect("family_invitation_detail", token=token)
    messages.success(request, f"You are now connected to {invitation.family.name}.")
    return redirect(f"{reverse('tree')}?family={invitation.family.slug}")


@login_required
def invitation_decline(request, token):
    if request.method != "POST":
        return HttpResponseBadRequest("Use POST to decline an invitation.")
    invitation = get_object_or_404(FamilyInvitation, token=token)
    try:
        decline_invitation(invitation, request.user)
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, str(exc))
        return redirect("family_invitation_detail", token=token)
    messages.success(request, "Invitation declined.")
    return redirect("tree")


@login_required
def invitation_ignore(request, token):
    if request.method != "POST":
        return HttpResponseBadRequest("Use POST to ignore an invitation.")
    invitation = get_object_or_404(FamilyInvitation, token=token)
    try:
        ignore_invitation(invitation, request.user)
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, str(exc))
        return redirect("family_invitation_detail", token=token)
    messages.success(request, "Invitation ignored.")
    return redirect("tree")


@login_required
def switch_family(request, slug):
    if request.method != "POST":
        return HttpResponseBadRequest("Use POST to switch family.")
    family = Family.objects.filter(slug=slug, memberships__user=request.user).first()
    if not family:
        raise Http404("Family not found.")
    request.session["current_family_slug"] = family.slug
    return redirect(f"{reverse('tree')}?family={family.slug}")


def signup(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.email = form.cleaned_data["email"]
            user.save(update_fields=["email"])
            login(request, user)
            return redirect("tree")
    else:
        form = SignupForm()
    return render(request, "registration/signup.html", {"form": form})


def _current_family(request):
    family = current_family_for_user(
        request.user,
        request.GET.get("family") or request.session.get("current_family_slug"),
    )
    if not family:
        raise Http404("Family not found.")
    return family


def _add_form_error(form, exc):
    if hasattr(exc, "messages"):
        message = "; ".join(exc.messages)
    else:
        message = str(exc)
    form.add_error(None, message)


def _render_invite_success(request, invitation):
    invitation_url = request.build_absolute_uri(
        reverse("family_invitation_detail", args=[invitation.token])
    )
    return render(
        request,
        "families/partials/invite_success_sheet.html",
        {
            "invitation": invitation,
            "invitation_url": invitation_url,
        },
    )


def _render_relative_success(request, person, invitation=None):
    invitation_url = ""
    if invitation:
        invitation_url = request.build_absolute_uri(
            reverse("family_invitation_detail", args=[invitation.token])
        )
    return render(
        request,
        "families/partials/relative_success_sheet.html",
        {
            "person": person,
            "invitation": invitation,
            "invitation_url": invitation_url,
        },
    )
