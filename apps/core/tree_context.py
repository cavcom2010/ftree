from pathlib import Path

from django.conf import settings

from apps.core.homepage_context import build_homepage_context
from apps.families.models import Family
from apps.people.models import Person
from apps.relationships.models import Relationship


MAX_TREE_DEPTH = 4


def build_tree_context(user):
    family = _family_for_user(user)
    if not family or not Person.objects.filter(family=family).exists():
        return _tree_from_demo_context(build_homepage_context())

    people = list(Person.objects.filter(family=family).order_by("birth_date", "first_name", "last_name", "id"))
    anchor = _anchor_for_user(family, user)
    if not anchor:
        return {
            "family": family,
            "tree_only": True,
            "tree_anchor": None,
            "anchor_choices": [_person_choice(person) for person in people],
            "relative_generation_rows": [],
            "generation_count": 0,
            "people_count": len(people),
            "empty_state": False,
            "needs_anchor_choice": True,
        }

    graph = _relationship_graph(family, people)
    rows = _relative_generation_rows(anchor, graph)
    cards = {
        card["id"]: card
        for row in rows
        for card in row["people"]
    }

    return {
        "family": family,
        "tree_only": True,
        "tree_anchor": _person_card(anchor, graph, 0, "Me"),
        "relative_generation_rows": rows,
        "person_cards": cards,
        "generation_count": len(rows),
        "people_count": len(people),
        "empty_state": False,
        "needs_anchor_choice": False,
    }


def _family_for_user(user):
    if getattr(user, "is_authenticated", False):
        membership = (
            Family.objects.filter(memberships__user=user)
            .order_by("memberships__joined_at", "name")
            .first()
        )
        if membership:
            return membership
    return Family.objects.order_by("name").first()


def _anchor_for_user(family, user):
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
    siblings_by_person = {person.id: set() for person in people}

    relationships = Relationship.objects.filter(
        family=family,
        from_person_id__in=person_ids,
        to_person_id__in=person_ids,
    ).values_list("from_person_id", "to_person_id", "relationship_type")

    for from_id, to_id, relationship_type in relationships:
        if relationship_type == Relationship.Type.PARENT_CHILD:
            children_by_parent[from_id].add(to_id)
            parents_by_child[to_id].add(from_id)
        elif relationship_type == Relationship.Type.SPOUSE:
            partners_by_person[from_id].add(to_id)
            partners_by_person[to_id].add(from_id)
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
        "siblings_by_person": siblings_by_person,
    }


def _relative_generation_rows(anchor, graph):
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


def _person_card(person, graph, generation_number, relationship_label):
    parent_ids = graph["parents_by_child"].get(person.id, set())
    partner_ids = graph["partners_by_person"].get(person.id, set())
    child_ids = graph["children_by_parent"].get(person.id, set())
    sibling_ids = graph["siblings_by_person"].get(person.id, set())

    return {
        "id": person.id,
        "full_name": person.full_name,
        "first_name": person.first_name,
        "initials": _initials(person.first_name, person.last_name),
        "relationship_label": relationship_label,
        "generation_label": _generation_label(generation_number),
        "life_years": _life_years(person),
        "location": person.current_place or person.birth_place or "Location unknown",
        "avatar_url": _profile_photo_url(person),
        "is_anchor": relationship_label == "Me",
        "parents": [_mini_person(graph["people_by_id"][person_id]) for person_id in parent_ids if person_id in graph["people_by_id"]],
        "partners": [_mini_person(graph["people_by_id"][person_id]) for person_id in partner_ids if person_id in graph["people_by_id"]],
        "children": [_mini_person(graph["people_by_id"][person_id]) for person_id in child_ids if person_id in graph["people_by_id"]],
        "siblings": [_mini_person(graph["people_by_id"][person_id]) for person_id in sibling_ids if person_id in graph["people_by_id"]],
        "parent_count": len(parent_ids),
        "partner_count": len(partner_ids),
        "child_count": len(child_ids),
        "sibling_count": len(sibling_ids),
    }


def _mini_person(person):
    return {
        "id": person.id,
        "full_name": person.full_name,
        "initials": _initials(person.first_name, person.last_name),
    }


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
        return "Ancestor row. Slide horizontally to inspect every branch."
    return "Descendant row. Slide horizontally to inspect every branch."


def _relationship_label(generation_number, is_anchor):
    if is_anchor:
        return "Me"
    labels = {
        -2: "Grandparent",
        -1: "Parent",
        0: "Sibling",
        1: "Child",
        2: "Grandchild",
        3: "Great-grandchild",
    }
    if generation_number < -2:
        return "Ancestor"
    if generation_number > 3:
        return "Descendant"
    return labels.get(generation_number, "Relative")


def _life_years(person):
    if not person.birth_date and not person.death_date:
        return ""
    start = str(person.birth_date.year) if person.birth_date else ""
    end = str(person.death_date.year) if person.death_date else "Living"
    return f"{start} - {end}".strip(" -")


def _initials(first_name, last_name):
    return f"{first_name[:1]}{last_name[:1]}".upper() or "FM"


def _tree_from_demo_context(context):
    rows = []
    for section in context.get("generation_sections", []):
        people_by_id = {}
        for row in section["rows"]:
            for person in row["people"]:
                people_by_id[person["id"]] = _demo_person_card(person, section["label"])
        rows.append(
            {
                "number": _demo_generation_number(section["label"]),
                "label": section["label"],
                "title": section["title"],
                "subtitle": section["subtitle"],
                "people": list(people_by_id.values()),
            }
        )

    context.update(
        {
            "tree_only": True,
            "tree_anchor": _demo_person_card(context["root_person"], "Gen 0"),
            "relative_generation_rows": rows,
            "needs_anchor_choice": False,
        }
    )
    return context


def _demo_person_card(person, generation_label):
    return {
        "id": person["id"],
        "full_name": person["name"],
        "first_name": person["name"].split(" ")[0],
        "initials": person["initials"],
        "relationship_label": person["relationship_label"],
        "generation_label": generation_label,
        "life_years": "",
        "location": "Family tree",
        "avatar_url": _safe_demo_avatar_url(person.get("avatar_url", "")),
        "is_anchor": person["relationship_label"] == "Root person",
        "parents": [],
        "partners": [],
        "children": [],
        "siblings": [],
        "parent_count": 0,
        "partner_count": 0,
        "child_count": 0,
        "sibling_count": 0,
    }


def _demo_generation_number(label):
    if label == "Gen 0":
        return 0
    if label.startswith("Gen +"):
        return int(label.replace("Gen +", ""))
    if label.startswith("Gen -"):
        return int(label.replace("Gen ", ""))
    return 0


def _safe_demo_avatar_url(url):
    if not url:
        return ""
    media_url = getattr(settings, "MEDIA_URL", "/media/")
    if url.startswith(media_url):
        relative_path = url.removeprefix(media_url).lstrip("/")
        if not (Path(settings.MEDIA_ROOT) / relative_path).exists():
            return ""
    return url
