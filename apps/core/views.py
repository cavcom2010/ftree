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
    family_slug = request.session.get("current_family_slug")
    if request.user.is_authenticated:
        family, _created_or_repaired = _ensure_starter_tree_for_user(
            request.user,
            family_slug=family_slug,
        )
        request.session["current_family_slug"] = family.slug
        family_slug = family.slug

    return render(request, "core/home.html", build_homepage_context(request.user, family_slug=family_slug))


@login_required
def tree(request):
    family_slug = request.GET.get("family") or request.session.get("current_family_slug")
    if request.GET.get("family"):
        request.session["current_family_slug"] = request.GET["family"]

    family, created_or_repaired = _ensure_starter_tree_for_user(
        request.user,
        family_slug=family_slug,
    )
    request.session["current_family_slug"] = family.slug

    context = build_tree_context(request.user, family_slug=family.slug)
    context["show_tree_onboarding"] = bool(
        created_or_repaired
        or (
            context.get("tree_anchor")
            and context.get("can_invite_relatives")
            and context.get("people_count", 0) <= 1
        )
    )

    return render(request, "tree/home.html", context)


@transaction.atomic
def _ensure_starter_tree_for_user(user, family_slug=None):
    membership_qs = FamilyMembership.objects.filter(user=user).select_related("family", "person")
    membership = None
    if family_slug:
        membership = membership_qs.filter(family__slug=family_slug).first()
    if not membership:
        membership = membership_qs.order_by("joined_at", "family__name").first()

    if not membership:
        return _create_starter_tree_for_user(user), True

    family = membership.family
    if not Person.objects.filter(family=family).exists():
        person = _create_person_for_user(user, family)
        membership.person = person
        membership.save(update_fields=["person"])
        return family, True

    if membership.person_id:
        return family, False

    return family, False


@transaction.atomic
def _create_starter_tree_for_user(user):
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


def _create_person_for_user(user, family):
    first_name, last_name = _person_name_for_user(user)
    return Person.objects.create(
        family=family,
        first_name=first_name,
        last_name=last_name,
        created_by=user,
        is_private=True,
    )


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
