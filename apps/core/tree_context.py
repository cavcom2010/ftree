from pathlib import Path

from django.conf import settings
from django.db.models import Count

from apps.core.homepage_context import build_homepage_context
from apps.families.models import Family
from apps.families.services import (
    can_invite,
    current_family_for_user,
    invitation_counts_for_people,
    memberships_by_person,
    pending_invitations_for_user,
)
from apps.people.models import Person
from apps.relationships.models import Relationship


MAX_TREE_DEPTH = 4
PARENT_TREE_TYPES = {
    Relationship.Type.PARENT_CHILD,
    Relationship.Type.ADOPTIVE_PARENT,
    Relationship.Type.STEP_PARENT,
    Relationship.Type.GUARDIAN,
}
PARTNER_TREE_TYPES = {
    Relationship.Type.SPOUSE,
    Relationship.Type.PARTNER,
    Relationship.Type.EX_PARTNER,
    Relationship.Type.CO_PARENT,
}


def build_tree_context(user, family_slug=None, anchor_id=None, global_admin_view=False):
    family = _family_for_user(user, family_slug=family_slug, global_admin_view=global_admin_view)
    if not family or not Person.objects.filter(family=family).exists():
        return _tree_from_demo_context(build_homepage_context())

    people = list(Person.objects.filter(family=family).order_by("birth_date", "first_name", "last_name", "id"))
    anchor = _anchor_for_user(family, user, anchor_id=anchor_id, global_admin_view=global_admin_view)
    available_families = _available_families(user, global_admin_view=global_admin_view)
    received_invitations = list(pending_invitations_for_user(user)[:8])
    user_can_invite = can_invite(family, user)
    if not anchor:
        return {
            "family": family,
            "tree_only": True,
            "tree_anchor": None,
            "anchor_choices": [_person_choice(person) for person in people],
            "available_families": available_families,
            "received_invitations": received_invitations,
            "can_invite_relatives": user_can_invite,
            "relative_generation_rows": [],
            "generation_count": 0,
            "people_count": len(people),
            "empty_state": False,
            "needs_anchor_choice": True,
            "needs_family_choice": False,
            "is_global_admin_view": global_admin_view,
            "admin_anchor_choices": [],
        }

    graph = _relationship_graph(family, people)
    invite_map = invitation_counts_for_people(family, people)
    membership_map = memberships_by_person(family, people)
    rows = _relative_generation_rows(
        anchor,
        graph,
        membership_map=membership_map,
        invite_map=invite_map,
        current_user=user,
        can_invite_relatives=user_can_invite,
    )
    cards = {
        card["id"]: card
        for row in rows
        for card in row["people"]
    }

    return {
        "family": family,
        "tree_only": True,
        "tree_anchor": _person_card(
            anchor,
            graph,
            0,
            "Me",
            membership_map=membership_map,
            invite_map=invite_map,
            current_user=user,
            can_invite_relatives=user_can_invite,
        ),
        "relative_generation_rows": rows,
        "person_cards": cards,
        "available_families": available_families,
        "received_invitations": received_invitations,
        "can_invite_relatives": user_can_invite,
        "generation_count": len(rows),
        "people_count": len(people),
        "empty_state": False,
        "needs_anchor_choice": False,
        "needs_family_choice": False,
        "is_global_admin_view": global_admin_view,
        "admin_anchor_choices": [_person_choice(person) for person in people] if global_admin_view else [],
    }


def _family_for_user(user, family_slug=None, global_admin_view=False):
    if global_admin_view and family_slug:
        return Family.objects.filter(slug=family_slug).first()
    return current_family_for_user(user, family_slug=family_slug)


def _available_families(user, global_admin_view=False):
    if not getattr(user, "is_authenticated", False):
        return []
    if global_admin_view:
        return list(
            Family.objects.annotate(people_count=Count("people"))
            .order_by("name", "id")
            .distinct()
        )
    return list(Family.objects.filter(memberships__user=user).order_by("name").distinct())


def _anchor_for_user(family, user, anchor_id=None, global_admin_view=False):
    if global_admin_view:
        if anchor_id:
            anchor = Person.objects.filter(family=family, id=anchor_id).first()
            if anchor:
                return anchor
        membership = family.memberships.select_related("person").filter(user=user).first()
        if membership and membership.person:
            return membership.person
        return Person.objects.filter(family=family).order_by("birth_date", "first_name", "last_name", "id").first()

    if getattr(user, "is_authenticated", False):
        membership = (
            family.memberships.select_related("person")
            .filter(user=user)
            .first()
        )
        if membership and membership.person:
            return membership.person
        return None

    membership = family.memberships.select_related("person").filter(person__isnull=False).first()
    return membership.person if membership else None


def _relationship_graph(family, people):
    person_ids = {person.id for person in people}
    parents_by_child = {person.id: set() for person in people}
    children_by_parent = {person.id: set() for person in people}
    partners_by_person = {person.id: set() for person in people}
    partner_types_by_person = {person.id: {} for person in people}
    siblings_by_person = {person.id: set() for person in people}

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
            partners_by_person[from_id].add(to_id)
            partners_by_person[to_id].add(from_id)
            _store_partner_type(partner_types_by_person, from_id, to_id, relationship_type)
            _store_partner_type(partner_types_by_person, to_id, from_id, relationship_type)
        elif relationship_type == Relationship.Type.SIBLING:
            siblings_by_person[from_id].add(to_id)
            siblings_by_person[to_id].add(from_id)

    for child_id, parent_ids in parents_by_child.items():
        for parent_id in parent_ids:
            siblings_by_person[child_id].update(children_by_parent.get(parent_id, set()))
        siblings_by_person[child_id].discard(child_id)

    people_by_id = {person.id: person for person in people}
    return {
        "people_by_id": people_by_id,
        "parents_by_child": parents_by_child,
        "children_by_parent": children_by_parent,
        "partners_by_person": partners_by_person,
        "partner_types_by_person": partner_types_by_person,
        "siblings_by_person": siblings_by_person,
    }


def _relative_generation_rows(anchor, graph, membership_map, invite_map, current_user, can_invite_relatives):
    people_by_id = graph["people_by_id"]
    rows_by_number = {0: _gen_zero_people(anchor, graph)}

    current_ids = {anchor.id}
    for level in range(1, MAX_TREE_DEPTH + 1):
        parent_ids = _next_related_ids(current_ids, graph["parents_by_child"])
        if not parent_ids:
            break
        rows_by_number[-level] = _people_from_ids(parent_ids, people_by_id)
        current_ids = parent_ids

    current_ids = {anchor.id}
    for level in range(1, MAX_TREE_DEPTH + 1):
        child_ids = _next_related_ids(current_ids, graph["children_by_parent"])
        if not child_ids:
            break
        rows_by_number[level] = _people_from_ids(child_ids, people_by_id)
        current_ids = child_ids

    rows = []
    for generation_number in sorted(rows_by_number):
        people = rows_by_number[generation_number]
        if not people:
            continue
        rows.append(
            {
                "number": generation_number,
                "label": _generation_label(generation_number),
                "title": _generation_title(generation_number),
                "subtitle": _generation_subtitle(generation_number),
                "people": [
                    _person_card(
                        person,
                        graph,
                        generation_number,
                        _relationship_label(generation_number, person.id == anchor.id),
                        membership_map=membership_map,
                        invite_map=invite_map,
                        current_user=current_user,
                        can_invite_relatives=can_invite_relatives,
                    )
                    for person in people
                ],
            }
        )
    return rows


def _gen_zero_people(anchor, graph):
    people_by_id = graph["people_by_id"]
    sibling_ids = set(graph["siblings_by_person"].get(anchor.id, set()))
    sibling_ids.add(anchor.id)
    return _people_from_ids(sibling_ids, people_by_id)


def _next_related_ids(current_ids, relationship_map):
    related_ids = set()
    for person_id in current_ids:
        related_ids.update(relationship_map.get(person_id, set()))
    return related_ids


def _people_from_ids(person_ids, people_by_id):
    return sorted(
        (people_by_id[person_id] for person_id in person_ids if person_id in people_by_id),
        key=_person_order,
    )


def _person_order(person):
    return (
        person.birth_date is None,
        person.birth_date or "",
        person.first_name.lower(),
        person.last_name.lower(),
        person.id,
    )


def _person_card(
    person,
    graph,
    generation_number,
    relationship_label,
    membership_map=None,
    invite_map=None,
    current_user=None,
    can_invite_relatives=False,
):
    parent_ids = graph["parents_by_child"].get(person.id, set())
    partner_ids = graph["partners_by_person"].get(person.id, set())
    child_ids = graph["children_by_parent"].get(person.id, set())
    sibling_ids = graph["siblings_by_person"].get(person.id, set())
    membership_map = membership_map or {}
    invite_map = invite_map or {}
    membership = membership_map.get(person.id)
    invitation = invite_map.get(person.id)
    is_current_user = bool(
        membership
        and getattr(current_user, "is_authenticated", False)
        and membership.user_id == current_user.id
    )

    return {
        "id": person.id,
        "full_name": person.full_name,
        "maiden_name": person.maiden_name,
        "first_name": person.first_name,
        "initials": _initials(person.first_name, person.last_name),
        "relationship_label": relationship_label,
        "generation_label": _generation_label(generation_number),
        "life_years": _life_years(person),
        "is_living": person.is_living,
        "death_date": person.death_date,
        "life_status": _life_status(person),
        "location": person.current_place or person.birth_place or "Location unknown",
        "avatar_url": _profile_photo_url(person),
        "is_anchor": relationship_label == "Me",
        "is_connected": bool(membership),
        "is_current_user": is_current_user,
        "connected_user": membership.user.username if membership else "",
        "connection_label": _connection_label(membership, invitation, is_current_user),
        "has_pending_invite": bool(invitation),
        "pending_invite_label": invitation.invitee_label if invitation else "",
        "can_invite": can_invite_relatives and person.is_living and not membership and not invitation,
        "can_edit_name": is_current_user or can_invite_relatives,
        "parents": [_mini_person(graph["people_by_id"][person_id]) for person_id in parent_ids if person_id in graph["people_by_id"]],
        "partners": [
            _mini_person(
                graph["people_by_id"][person_id],
                relationship_label=_partner_relationship_label(graph, person.id, person_id),
                shared_child_names=_shared_child_names(graph, person.id, person_id),
            )
            for person_id in partner_ids
            if person_id in graph["people_by_id"]
        ],
        "children": [_mini_person(graph["people_by_id"][person_id]) for person_id in child_ids if person_id in graph["people_by_id"]],
        "siblings": [_mini_person(graph["people_by_id"][person_id]) for person_id in sibling_ids if person_id in graph["people_by_id"]],
        "parent_count": len(parent_ids),
        "partner_count": len(partner_ids),
        "child_count": len(child_ids),
        "sibling_count": len(sibling_ids),
    }


def _connection_label(membership, invitation, is_current_user):
    if is_current_user:
        return "You"
    if membership:
        return f"Connected to {membership.user.username}"
    if invitation:
        return f"Pending invite to {invitation.invitee_label}"
    return "Unclaimed"


def _mini_person(person, relationship_label="", shared_child_names=None):
    return {
        "id": person.id,
        "full_name": person.full_name,
        "initials": _initials(person.first_name, person.last_name),
        "relationship_label": relationship_label,
        "life_status": _life_status(person),
        "shared_child_names": shared_child_names or [],
    }


def _store_partner_type(partner_types_by_person, person_id, partner_id, relationship_type):
    existing = partner_types_by_person[person_id].get(partner_id)
    if not existing or _partner_type_priority(relationship_type) < _partner_type_priority(existing):
        partner_types_by_person[person_id][partner_id] = relationship_type


def _partner_type_priority(relationship_type):
    priorities = {
        Relationship.Type.SPOUSE: 0,
        Relationship.Type.PARTNER: 1,
        Relationship.Type.EX_PARTNER: 2,
        Relationship.Type.CO_PARENT: 3,
    }
    return priorities.get(relationship_type, 99)


def _partner_relationship_label(graph, person_id, partner_id):
    relationship_type = graph["partner_types_by_person"].get(person_id, {}).get(partner_id)
    labels = {
        Relationship.Type.SPOUSE: "Spouse",
        Relationship.Type.PARTNER: "Partner",
        Relationship.Type.EX_PARTNER: "Ex-partner",
        Relationship.Type.CO_PARENT: "Co-parent",
    }
    return labels.get(relationship_type, "Partner")


def _shared_child_names(graph, person_id, partner_id):
    shared_child_ids = graph["children_by_parent"].get(person_id, set()) & graph["children_by_parent"].get(partner_id, set())
    return [
        graph["people_by_id"][child_id].full_name
        for child_id in sorted(shared_child_ids)
        if child_id in graph["people_by_id"]
    ][:3]


def _profile_photo_url(person):
    if not person.profile_photo:
        return ""
    try:
        if person.profile_photo.storage.exists(person.profile_photo.name):
            return person.profile_photo.url
    except Exception:
        return ""
    return ""


def _person_choice(person):
    return {
        "id": person.id,
        "full_name": person.full_name,
        "initials": _initials(person.first_name, person.last_name),
        "life_years": _life_years(person),
    }


def _generation_label(number):
    if number == 0:
        return "Gen 0"
    if number > 0:
        return f"Gen +{number}"
    return f"Gen {number}"


def _generation_title(number):
    titles = {
        -4: "Great-great-grandparents",
        -3: "Great-grandparents",
        -2: "Grandparents",
        -1: "Parents",
        0: "My generation",
        1: "Children",
        2: "Grandchildren",
        3: "Great-grandchildren",
        4: "Future descendants",
    }
    return titles.get(number, "Relatives")


def _generation_subtitle(number):
    if number == 0:
        return "You and siblings in one independent row."
    if number < 0:
        return "Ancestors above your Gen 0 anchor."
    return "Descendants below your Gen 0 anchor."


def _relationship_label(generation_number, is_anchor=False):
    if is_anchor:
        return "Me"
    labels = {
        -4: "Great-great-grandparent",
        -3: "Great-grandparent",
        -2: "Grandparent",
        -1: "Parent",
        0: "Sibling",
        1: "Child",
        2: "Grandchild",
        3: "Great-grandchild",
        4: "Descendant",
    }
    return labels.get(generation_number, "Relative")


def _life_years(person):
    if person.birth_date and person.death_date:
        return f"{person.birth_date.year}–{person.death_date.year}"
    if person.birth_date:
        return f"Born {person.birth_date.year}"
    return ""


def _life_status(person):
    if person.death_date:
        return f"Died {person.death_date.strftime('%d %b %Y')}"
    if not person.is_living:
        return "Deceased"
    return ""


def _initials(first_name, last_name):
    letters = f"{(first_name or 'F')[:1]}{(last_name or '')[:1]}".upper()
    return letters[:2]


def _tree_from_demo_context(context):
    rows = context.get("generation_rows", [])
    return {
        "family": context.get("family"),
        "tree_only": True,
        "tree_anchor": None,
        "relative_generation_rows": rows,
        "person_cards": {},
        "available_families": [],
        "received_invitations": [],
        "can_invite_relatives": False,
        "generation_count": len(rows),
        "people_count": context.get("stats", {}).get("people", 0),
        "empty_state": not rows,
        "needs_anchor_choice": False,
        "needs_family_choice": False,
        "is_global_admin_view": False,
        "admin_anchor_choices": [],
    }


def _seed_photo_url(filename):
    path = Path(settings.MEDIA_ROOT) / "demo" / filename
    if path.exists():
        return f"{settings.MEDIA_URL}demo/{filename}"
    return ""
