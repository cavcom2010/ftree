import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.families.connection_services import approve_connection_request, create_connection_request, reject_connection_request
from apps.families.discovery_forms import ConnectionRequestForm, StartTreeIdentityForm
from apps.families.matching import find_possible_family_matches
from apps.families.models import Family, FamilyConnectionRequest, FamilyMembership
from apps.families.public_discovery import (
    can_public_view_family,
    manager_can_review_requests,
    public_family_cards,
    public_tree_context,
    surname_family_cards,
)
from apps.people.models import Person


def public_tree_gallery(request):
    query = request.GET.get("q", "")
    cards = public_family_cards(query=query)
    return render(
        request,
        "families/public_tree_gallery.html",
        {
            "query": query,
            "family_cards": cards,
            "public_family_count": len(cards),
        },
    )


def public_tree_detail(request, slug):
    family = get_object_or_404(Family, slug=slug)
    if not can_public_view_family(family):
        messages.info(request, "That family tree is private. You can request access from the owner if they share an invite.")
        return redirect("tree")
    context = public_tree_context(family)
    context["tree_json"] = json.dumps(context["tree_json"])
    return render(request, "tree/home.html", context)


def surname_detail(request, surname_slug):
    surname = surname_slug.replace("-", " ").strip().title()
    cards = surname_family_cards(surname)
    return render(
        request,
        "families/surname_detail.html",
        {
            "surname": surname,
            "family_cards": cards,
        },
    )


@login_required
def start_or_find_tree(request):
    suggestions = []
    form = StartTreeIdentityForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        suggestions = find_possible_family_matches(form.cleaned_data)
        if not suggestions:
            messages.info(request, "No strong public matches yet. You can create a private tree or search public surnames.")
    return render(
        request,
        "families/start_find_tree.html",
        {
            "form": form,
            "suggestions": suggestions,
        },
    )


@login_required
def request_connection(request, slug):
    family = get_object_or_404(Family, slug=slug)
    if not can_public_view_family(family):
        messages.error(request, "This tree is not open for public connection requests.")
        return redirect("tree")
    if not family.allow_connection_requests:
        messages.info(request, "This family tree is not accepting connection requests right now.")
        return redirect("public_tree_detail", slug=family.slug)

    form = ConnectionRequestForm(request.POST or None, user=request.user)
    suggestions = []
    if request.method == "POST" and form.is_valid():
        suggestions = [
            suggestion
            for suggestion in find_possible_family_matches(form.cleaned_data, include_private=True, limit=12)
            if suggestion["family"].id == family.id
        ]
        selected_person = _selected_suggestion_person(request, family)
        suggestion = _suggestion_for_person(suggestions, selected_person) or (suggestions[0] if suggestions else {})
        try:
            create_connection_request(
                family=family,
                user=request.user,
                cleaned_data=form.cleaned_data,
                suggestion=suggestion,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Your connection request has been sent to the tree owner.")
            return redirect("public_tree_detail", slug=family.slug)

    return render(
        request,
        "families/request_connection.html",
        {
            "family": family,
            "form": form,
            "suggestions": suggestions,
        },
    )


@login_required
def connection_requests_dashboard(request):
    manageable_family_ids = _manageable_family_ids(request.user)
    requests = (
        FamilyConnectionRequest.objects.filter(family_id__in=manageable_family_ids)
        .select_related("family", "user", "suggested_person")
        .order_by("status", "-created_at")[:100]
    )
    return render(
        request,
        "families/connection_requests.html",
        {
            "connection_requests": requests,
        },
    )


@login_required
def review_connection_request(request, request_id, action):
    request_obj = get_object_or_404(
        FamilyConnectionRequest.objects.select_related("family", "user", "suggested_person"),
        id=request_id,
    )
    if request.method != "POST":
        return redirect("family_connection_requests")
    try:
        if action == "approve":
            approve_connection_request(request_obj, request.user)
            messages.success(request, "Connection request approved.")
        elif action == "reject":
            reject_connection_request(request_obj, request.user, reviewer_note=request.POST.get("reviewer_note", ""))
            messages.info(request, "Connection request rejected.")
        else:
            messages.error(request, "Unknown review action.")
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, str(exc))
    return redirect("family_connection_requests")


def _manageable_family_ids(user):
    if user.is_staff or user.is_superuser:
        return list(Family.objects.values_list("id", flat=True))
    return list(
        FamilyMembership.objects.filter(
            user=user,
            role__in=[
                FamilyMembership.Role.OWNER,
                FamilyMembership.Role.ADMIN,
                FamilyMembership.Role.BRANCH_ADMIN,
            ],
        ).values_list("family_id", flat=True)
    )


def _selected_suggestion_person(request, family):
    person_id = request.POST.get("suggested_person")
    if not person_id:
        return None
    return Person.objects.filter(family=family, id=person_id).first()


def _suggestion_for_person(suggestions, person):
    if not person:
        return None
    for suggestion in suggestions:
        if suggestion["person"].id == person.id:
            return suggestion
    return {"person": person, "score": 0, "reasons": ["selected by requester"]}
