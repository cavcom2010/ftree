import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
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
        if not (_is_global_tree_admin(request.user) and not _has_family_membership(request.user)):
            family, _created_or_repaired = _ensure_starter_tree_for_user(
                request.user,
                family_slug=family_slug,
            )
            request.session["current_family_slug"] = family.slug
            family_slug = family.slug

    return render(request, "core/home.html", build_homepage_context(request.user, family_slug=family_slug))


@login_required
def tree(request):
    is_global_admin = _is_global_tree_admin(request.user)
    if is_global_admin:
        explicit_family_slug = request.GET.get("family")
        if not explicit_family_slug and not _has_family_membership(request.user):
            return render(request, "tree/home.html", _admin_family_picker_context(request.user))

        if explicit_family_slug and not Family.objects.filter(slug=explicit_family_slug).exists():
            return render(request, "tree/home.html", _admin_family_picker_context(request.user))

        if explicit_family_slug:
            request.session["current_family_slug"] = explicit_family_slug
            context = build_tree_context(
                request.user,
                family_slug=explicit_family_slug,
                anchor_id=_anchor_id_from_request(request),
                global_admin_view=True,
            )
            context["show_tree_onboarding"] = False
            tree_data = {"people": [], "root_id": None}
            family = Family.objects.filter(slug=explicit_family_slug).first()
            if family and not context.get("needs_anchor_choice"):
                anchor_person = _resolve_tree_anchor(request, family, context)
                if anchor_person:
                    tree_data = _tree_data_for_family(family, anchor_person)
                    context["tree_anchor_person"] = anchor_person
            context["tree_json"] = json.dumps(tree_data)
            return render(request, "tree/home.html", context)

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

    tree_data = {"people": [], "root_id": None}
    if (
        family
        and not context.get("needs_tree_setup")
        and not context.get("needs_family_choice")
        and not context.get("needs_anchor_choice")
    ):
        anchor_person = _resolve_tree_anchor(request, family, context)
        if anchor_person:
            tree_data = _tree_data_for_family(family, anchor_person)
            context["tree_anchor_person"] = anchor_person

    context["tree_json"] = json.dumps(tree_data)

    return render(request, "tree/home.html", context)


def _is_global_tree_admin(user):
    return bool(getattr(user, "is_authenticated", False) and (user.is_staff or user.is_superuser))


def _has_family_membership(user):
    return FamilyMembership.objects.filter(user=user).exists()


def _anchor_id_from_request(request):
    value = request.GET.get("anchor")
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _admin_family_picker_context(user):
    families = list(
        Family.objects.annotate(people_count=Count("people"))
        .order_by("name", "id")
    )
    return {
        "family": None,
        "tree_only": True,
        "tree_anchor": None,
        "anchor_choices": [],
        "available_families": families,
        "admin_family_choices": families,
        "admin_anchor_choices": [],
        "received_invitations": list(pending_invitations_for_user(user)[:8]),
        "can_invite_relatives": False,
        "relative_generation_rows": [],
        "person_cards": {},
        "generation_count": 0,
        "people_count": sum(family.people_count for family in families),
        "empty_state": not families,
        "needs_anchor_choice": False,
        "needs_family_choice": True,
        "needs_tree_setup": False,
        "show_tree_onboarding": False,
        "is_global_admin_view": True,
    }


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
    if membership.person_id:
        return family, False

    person = (
        Person.objects.filter(family=family, created_by=user)
        .order_by("birth_date", "first_name", "last_name", "id")
        .first()
    )
    if not person:
        person = _create_person_for_user(user, family)

    membership.person = person
    membership.save(update_fields=["person"])
    return family, True


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


# ---------------------------------------------------------------------------
# Radial tree JSON helpers
# ---------------------------------------------------------------------------

PARENT_TREE_TYPES = {
    "parent_child",
    "adoptive_parent",
    "step_parent",
    "guardian",
}

PARTNER_TREE_TYPES = {
    "spouse",
    "partner",
    "ex_partner",
    "co_parent",
}


def _resolve_tree_anchor(request, family, context=None):
    """Return the Person that should be the Gen 0 anchor for the radial tree."""
    context = context or {}
    explicit_anchor = _anchor_id_from_request(request)
    is_global_admin = _is_global_tree_admin(request.user)

    if is_global_admin and explicit_anchor:
        return Person.objects.filter(family=family, id=explicit_anchor).first()

    membership = (
        family.memberships.select_related("person").filter(user=request.user).first()
    )
    if membership and membership.person:
        return membership.person

    return (
        Person.objects.filter(family=family)
        .order_by("birth_date", "first_name", "last_name", "id")
        .first()
    )


def _compute_generation_map(anchor, people, parents_by_child, children_by_parent, partners, siblings):
    """Compute generation numbers relative to the anchor (anchor=0, parents>0, children<0)."""
    gen_map = {anchor.id: 0}
    queue = [anchor.id]
    visited = {anchor.id}

    while queue:
        person_id = queue.pop(0)
        gen = gen_map[person_id]

        for parent_id in parents_by_child.get(person_id, set()):
            if parent_id not in gen_map:
                gen_map[parent_id] = gen + 1
            if parent_id not in visited:
                visited.add(parent_id)
                queue.append(parent_id)

        for child_id in children_by_parent.get(person_id, set()):
            if child_id not in gen_map:
                gen_map[child_id] = gen - 1
            if child_id not in visited:
                visited.add(child_id)
                queue.append(child_id)

        for sibling_id in siblings.get(person_id, set()):
            if sibling_id not in gen_map:
                gen_map[sibling_id] = gen
            if sibling_id not in visited:
                visited.add(sibling_id)
                queue.append(sibling_id)

        for partner_id in partners.get(person_id, set()):
            if partner_id not in gen_map:
                gen_map[partner_id] = gen
            if partner_id not in visited:
                visited.add(partner_id)
                queue.append(partner_id)

    return gen_map


def _tree_data_for_family(family, anchor):
    """Return the JSON payload consumed by the radial tree renderer."""
    from apps.relationships.models import Relationship

    people = list(Person.objects.filter(family=family))
    person_ids = {person.id for person in people}

    parents_by_child = {person.id: set() for person in people}
    children_by_parent = {person.id: set() for person in people}
    partners = {person.id: set() for person in people}
    siblings = {person.id: set() for person in people}

    relationships = Relationship.objects.filter(
        family=family,
        from_person_id__in=person_ids,
        to_person_id__in=person_ids,
    ).values_list("from_person_id", "to_person_id", "relationship_type")

    for from_id, to_id, relationship_type in relationships:
        if relationship_type in PARENT_TREE_TYPES:
            children_by_parent[from_id].add(to_id)
            parents_by_child[to_id].add(from_id)
        elif relationship_type in PARTNER_TREE_TYPES:
            partners[from_id].add(to_id)
            partners[to_id].add(from_id)
        elif relationship_type == "sibling":
            siblings[from_id].add(to_id)
            siblings[to_id].add(from_id)

    for child_id, parent_ids in parents_by_child.items():
        for parent_id in parent_ids:
            siblings[child_id].update(children_by_parent.get(parent_id, set()))
        siblings[child_id].discard(child_id)

    gen_map = _compute_generation_map(
        anchor, people, parents_by_child, children_by_parent, partners, siblings
    )

    return {
        "people": [p.to_tree_dict(generation=gen_map.get(p.id, 0)) for p in people],
        "root_id": str(anchor.id),
    }


@login_required
def tree_json(request):
    """JSON API for the radial tree renderer."""
    is_global_admin = _is_global_tree_admin(request.user)
    explicit_family_slug = request.GET.get("family")

    if is_global_admin and explicit_family_slug:
        family = Family.objects.filter(slug=explicit_family_slug).first()
    else:
        family_slug = request.GET.get("family") or request.session.get("current_family_slug")
        if request.GET.get("family"):
            request.session["current_family_slug"] = request.GET["family"]
        family, _created = _ensure_starter_tree_for_user(
            request.user,
            family_slug=family_slug,
        )

    if not family:
        return JsonResponse({"people": [], "root_id": None})

    anchor = _resolve_tree_anchor(request, family)
    if not anchor:
        return JsonResponse({"people": [], "root_id": None})

    return JsonResponse(_tree_data_for_family(family, anchor))
