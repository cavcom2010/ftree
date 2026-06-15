from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render
from django.utils.text import slugify

from apps.core.homepage_context import build_homepage_context
from apps.core.tree_context import build_tree_context
from apps.families.models import Family, FamilyMembership
from apps.families.services import pending_invitations_for_user
from apps.people.models import Person


def home(request):
    return render(request, "core/home.html", build_homepage_context())


@login_required
def tree(request):
    family_slug = request.GET.get("family") or request.session.get("current_family_slug")
    if request.GET.get("family"):
        request.session["current_family_slug"] = request.GET["family"]

    show_tree_onboarding = False
    if not FamilyMembership.objects.filter(user=request.user).exists():
        family = _create_starter_tree_for_user(request.user)
        request.session["current_family_slug"] = family.slug
        request.session["tree_onboarding_seen"] = True
        family_slug = family.slug
        show_tree_onboarding = True

    context = build_tree_context(request.user, family_slug=family_slug)
    context["show_tree_onboarding"] = show_tree_onboarding

    return render(request, "tree/home.html", context)


@transaction.atomic
def _create_starter_tree_for_user(user):
    membership = FamilyMembership.objects.filter(user=user).select_related("family").first()
    if membership:
        return membership.family

    first_name, last_name = _person_name_for_user(user)
    family = Family.objects.create(
        name=f"{first_name}'s Family Tree",
        slug=_unique_family_slug(user),
        created_by=user,
    )
    person = Person.objects.create(
        family=family,
        first_name=first_name,
        last_name=last_name,
        created_by=user,
        is_private=True,
    )
    FamilyMembership.objects.create(
        family=family,
        user=user,
        person=person,
        role=FamilyMembership.Role.OWNER,
    )
    return family


def _person_name_for_user(user):
    display_name = user.get_full_name().strip()
    if not display_name:
        identity = user.email.split("@", 1)[0] if user.email else user.get_username()
        display_name = identity.replace(".", " ").replace("_", " ").replace("-", " ").strip().title()

    parts = [part for part in display_name.split() if part]
    if not parts:
        return "Me", "Family"
    if len(parts) == 1:
        return parts[0], "Family"
    return parts[0], " ".join(parts[1:])


def _unique_family_slug(user):
    base = slugify(f"{user.get_username()} family tree") or f"user-{user.pk}-family-tree"
    slug = base
    counter = 2
    while Family.objects.filter(slug=slug).exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def _empty_tree_context(user):
    return {
        "family": None,
        "tree_only": True,
        "tree_anchor": None,
        "anchor_choices": [],
        "available_families": [],
        "received_invitations": list(pending_invitations_for_user(user)[:8]),
        "can_invite_relatives": False,
        "relative_generation_rows": [],
        "generation_count": 0,
        "people_count": 0,
        "empty_state": True,
        "needs_anchor_choice": False,
        "needs_tree_setup": True,
        "show_tree_onboarding": False,
    }
