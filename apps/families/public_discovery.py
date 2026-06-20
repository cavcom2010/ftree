from collections import deque

from django.db.models import Count, Q
from django.urls import reverse

from apps.families.models import Family, FamilyInvitation, FamilyMembership
from apps.people.models import Person
from apps.relationships.models import Relationship


PUBLIC_VISIBILITIES = {
    Family.Visibility.DISCOVERABLE,
    Family.Visibility.PUBLIC_ANCESTORS,
    Family.Visibility.PUBLIC_SHOWCASE,
}

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


def public_family_queryset():
    return (
        Family.objects.filter(visibility__in=PUBLIC_VISIBILITIES)
        .annotate(
            people_count=Count("people", distinct=True),
            branch_count=Count("branches", distinct=True),
            story_count=Count("stories", distinct=True),
            memory_count=Count("memories", distinct=True),
        )
        .order_by("name", "id")
    )


def public_family_cards(query=""):
    families = public_family_queryset()
    query = (query or "").strip()
    if query:
        families = families.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(public_summary__icontains=query)
            | Q(origin_summary__icontains=query)
            | Q(main_surnames__icontains=query)
            | Q(maiden_surnames__icontains=query)
            | Q(regions__icontains=query)
        )
    return [_family_card(family) for family in families[:80]]


def surname_family_cards(surname):
    surname = (surname or "").strip()
    if not surname:
        return []
    families = public_family_queryset().filter(allow_public_surname_search=True).filter(
        Q(main_surnames__icontains=surname) | Q(people__last_name__iexact=surname)
    ).distinct()
    return [_family_card(family) for family in families[:80]]


def _family_card(family):
    surnames = _clean_list(family.main_surnames)
    if not surnames:
        surnames = list(
            Person.objects.filter(family=family)
            .exclude(last_name="")
            .values_list("last_name", flat=True)
            .distinct()
            .order_by("last_name")[:6]
        )
    return {
        "family": family,
        "name": family.name,
        "slug": family.slug,
        "summary": family.public_summary or family.description,
        "origin": family.public_origin_label,
        "surnames": surnames[:6],
        "people_count": getattr(family, "people_count", family.people.count()),
        "branch_count": getattr(family, "branch_count", family.branches.count()),
        "story_count": getattr(family, "story_count", family.stories.count()),
        "memory_count": getattr(family, "memory_count", family.memories.count()),
        "visibility_label": family.get_visibility_display(),
        "url": reverse("public_tree_detail", args=[family.slug]),
        "request_url": reverse("family_request_connection", args=[family.slug]),
    }


def _clean_list(values):
    return [str(value).strip() for value in (values or []) if str(value).strip()]


def can_public_view_family(family):
    return family and family.visibility in PUBLIC_VISIBILITIES


def public_tree_context(family):
    if not can_public_view_family(family):
        return None

    people = list(Person.objects.filter(family=family).prefetch_related("memories", "stories"))
    anchor = _public_anchor(people)
    tree_json = _public_tree_data_for_family(family, anchor, people) if anchor else {"people": [], "root_id": None}
    return {
        "family": family,
        "tree_only": True,
        "tree_json": tree_json,
        "tree_anchor": _public_anchor_card(anchor) if anchor else None,
        "tree_anchor_person": anchor,
        "available_families": [],
        "received_invitations": [],
        "can_invite_relatives": False,
        "relative_generation_rows": [],
        "person_cards": {},
        "generation_count": 0,
        "people_count": len(people),
        "empty_state": not people,
        "needs_anchor_choice": False,
        "needs_family_choice": False,
        "needs_tree_setup": False,
        "show_tree_onboarding": False,
        "is_global_admin_view": False,
        "is_public_tree": True,
        "public_tree_card": _family_card(family),
        "tree_pending_invitations": [],
        "tree_connected_memberships": [],
    }


def _public_anchor(people):
    public_people = [person for person in people if person.can_be_publicly_identified]
    if public_people:
        return sorted(public_people, key=lambda p: (p.birth_date is None, p.birth_date or p.created_at.date(), p.id))[0]
    return sorted(people, key=lambda p: (p.birth_date is None, p.birth_date or p.created_at.date(), p.id))[0] if people else None


def _public_anchor_card(person):
    if not person:
        return None
    return {
        "id": person.id,
        "full_name": person.public_display_name,
        "initials": "🔒" if not person.can_be_publicly_identified else _initials(person.first_name, person.last_name),
        "life_years": person.public_date_label,
    }


def _public_tree_data_for_family(family, anchor, people):
    if family.visibility == Family.Visibility.DISCOVERABLE or not family.show_public_tree_shape:
        return {"people": [_public_person_payload(anchor, 0)] if anchor else [], "root_id": str(anchor.id) if anchor else None}

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
        elif relationship_type == Relationship.Type.SIBLING:
            siblings[from_id].add(to_id)
            siblings[to_id].add(from_id)

    for child_id, parent_ids in parents_by_child.items():
        for parent_id in parent_ids:
            siblings[child_id].update(children_by_parent.get(parent_id, set()))
        siblings[child_id].discard(child_id)

    gen_map = _compute_generation_map(anchor, people, parents_by_child, children_by_parent, partners, siblings)
    people_by_id = {person.id: person for person in people}

    visible_people = []
    for person in people:
        if person.can_be_publicly_identified or family.show_living_private_placeholders:
            visible_people.append(person)

    visible_ids = {person.id for person in visible_people}

    payloads = []
    for person in visible_people:
        payload = _public_person_payload(person, gen_map.get(person.id, 99))
        father_id, mother_id = _public_parent_ids(person.id, parents_by_child, people_by_id, visible_ids)
        partner_id = _first_visible_id(partners.get(person.id, set()), visible_ids)
        payload.update(
            {
                "father_id": str(father_id) if father_id else None,
                "mother_id": str(mother_id) if mother_id else None,
                "partner_id": str(partner_id) if partner_id else None,
                "sibling_ids": [str(pid) for pid in sorted(siblings.get(person.id, set()) & visible_ids)],
                "child_ids": [str(pid) for pid in sorted(children_by_parent.get(person.id, set()) & visible_ids)],
            }
        )
        payloads.append(payload)

    return {"people": payloads, "root_id": str(anchor.id)}


def _compute_generation_map(anchor, people, parents_by_child, children_by_parent, partners, siblings):
    gen_map = {anchor.id: 0}
    queue = deque([anchor.id])
    visited = {anchor.id}

    while queue:
        person_id = queue.popleft()
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


def _public_person_payload(person, generation):
    payload = person.to_public_tree_dict(generation=generation)
    payload.update(
        {
            "role": "Public ancestor" if person.can_be_publicly_identified else "Private branch",
            "memory_count": person.memories.count() if person.can_be_publicly_identified else 0,
            "story_count": person.stories.count() if person.can_be_publicly_identified else 0,
            "social": {},
            "is_claimed": False,
            "claimed_by_me": False,
            "claimed_by": None,
            "can_edit": False,
            "can_delete": False,
            "can_add_relative": False,
            "can_invite": False,
            "can_set_anchor": False,
            "urls": {
                "drawer": reverse("family_request_connection", args=[person.family.slug]),
                "edit_name": "",
                "invite": "",
                "add_relative": {},
                "set_anchor": "",
                "descendants": "",
                "delete": "",
                "story_create": reverse("family_request_connection", args=[person.family.slug]),
            },
        }
    )
    return payload


def _public_parent_ids(person_id, parents_by_child, people_by_id, visible_ids):
    parents = [people_by_id[parent_id] for parent_id in parents_by_child.get(person_id, set()) if parent_id in people_by_id]
    father = next((p for p in sorted(parents, key=lambda p: (p.created_at, p.id)) if p.gender == Person.Gender.MALE and p.id in visible_ids), None)
    mother = next((p for p in sorted(parents, key=lambda p: (p.created_at, p.id)) if p.gender == Person.Gender.FEMALE and p.id in visible_ids), None)
    if not father and not mother:
        visible_parents = [p for p in parents if p.id in visible_ids]
        if visible_parents:
            father = visible_parents[0]
    return (father.id if father else None, mother.id if mother else None)


def _first_visible_id(values, visible_ids):
    for value in sorted(values):
        if value in visible_ids:
            return value
    return None


def _initials(first_name, last_name):
    letters = f"{(first_name or 'F')[:1]}{(last_name or '')[:1]}".upper()
    return letters[:2]


def manager_can_review_requests(family, user):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_staff or user.is_superuser:
        return True
    return FamilyMembership.objects.filter(
        family=family,
        user=user,
        role__in=[
            FamilyMembership.Role.OWNER,
            FamilyMembership.Role.ADMIN,
            FamilyMembership.Role.BRANCH_ADMIN,
        ],
    ).exists()


def pending_claimed_person_ids(family):
    return set(
        FamilyInvitation.objects.filter(
            family=family,
            status=FamilyInvitation.Status.PENDING,
        ).values_list("person_id", flat=True)
    )
