from datetime import date

from apps.families.services import current_family_for_user
from apps.memories.models import Memory
from apps.people.models import Person
from apps.relationships.models import Relationship
from apps.social.models import Activity
from apps.stories.models import Story


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
}
MAX_HOMEPAGE_DEPTH = 3


def build_homepage_context(user=None, family_slug=None):
    if getattr(user, "is_authenticated", False):
        family = current_family_for_user(user, family_slug=family_slug)
        if family and Person.objects.filter(family=family).exists():
            return _build_family_context(family, is_demo_context=False, user=user)
        return _build_empty_context(family)

    return _build_demo_context()


def _build_family_context(family, *, is_demo_context, user=None):
    people = list(
        Person.objects.filter(family=family)
        .prefetch_related("memories", "stories")
        .order_by("birth_date", "first_name", "last_name", "id")
    )
    if not people:
        return _build_empty_context(family)

    anchor = _anchor_for_user(family, user) or people[0]
    people_by_id = {person.id: person for person in people}
    parents_by_child, children_by_parent, siblings_by_person, partners_by_person = _family_relationship_maps(family, people_by_id)

    people_with_partners = {person_id for person_id, partner_ids in partners_by_person.items() if partner_ids}
    children_count_by_parent = {person_id: len(child_ids) for person_id, child_ids in children_by_parent.items()}

    generation_rows = _relative_generation_rows(
        anchor,
        people_by_id,
        parents_by_child=parents_by_child,
        children_by_parent=children_by_parent,
        siblings_by_person=siblings_by_person,
        people_with_partners=people_with_partners,
        children_count_by_parent=children_count_by_parent,
    )

    person_cards = {
        person.id: _person_card_from_model(person, _relationship_label(0, person.id == anchor.id))
        for person in people
    }
    root_card = _person_card_from_model(anchor, "Me")
    branch_panels = _build_branch_panels(family, person_cards)
    for panel in branch_panels:
        owner_id = panel["owner"]["source_id"]
        if owner_id in person_cards:
            person_cards[owner_id]["branch_panel"] = panel
            person_cards[owner_id]["branch_panel_id"] = panel["id"]

    memories = Memory.objects.filter(family=family).prefetch_related("people").order_by("-created_at")
    stories = Story.objects.filter(family=family).prefetch_related("people").order_by("-created_at")
    recent_activities = Activity.objects.filter(family=family).order_by("-created_at")[:6]
    memory_rails = [
        _memory_rail(
            "Videos",
            "Short clips attached to relatives and branches.",
            [_memory_item_from_memory(memory) for memory in memories.filter(memory_type=Memory.Type.VIDEO)[:6]],
        ),
        _memory_rail(
            "Photo memories",
            "Images that keep people connected to the tree.",
            [_memory_item_from_memory(memory) for memory in memories.filter(memory_type=Memory.Type.PHOTO)[:6]],
        ),
        _memory_rail(
            "Story posts",
            "Written memories tied back to relatives.",
            [_memory_item_from_story(story) for story in stories[:6]],
        ),
    ]

    close_family = _close_family_dashboard(
        anchor,
        people_by_id,
        parents_by_child=parents_by_child,
        children_by_parent=children_by_parent,
        siblings_by_person=siblings_by_person,
        partners_by_person=partners_by_person,
    )
    context_people = list(person_cards.values())
    photo_count = memories.filter(memory_type=Memory.Type.PHOTO).count()
    story_count = stories.count()
    generation_count = len(generation_rows)

    return {
        "family": family,
        "root_person": root_card,
        "right_panel": _right_panel(root_card, family, generation_count, is_demo_context=False),
        "today_cards": _today_cards_from_family(people),
        "stats": {
            "generations": generation_count,
            "people": len(context_people),
            "memories": memories.count() + stories.count(),
            "missing": close_family["profile_missing_count"],
        },
        "dashboard": close_family,
        "generation_sections": _generation_sections_from_rows(generation_rows),
        "generation_rows": generation_rows,
        "rows": _rows_from_generation_rows(generation_rows),
        "people": context_people,
        "branch_panels": branch_panels,
        "memory_rails": memory_rails,
        "memories": list(memories[:6]),
        "recent_activities": list(recent_activities),
        "top_achievers": [],
        "generation_count": generation_count,
        "people_count": len(context_people),
        "photo_count": photo_count,
        "story_count": story_count,
        "empty_state": False,
        "is_demo_context": is_demo_context,
    }


def _build_empty_context(family=None):
    return {
        "family": family,
        "root_person": None,
        "right_panel": _empty_right_panel(family),
        "today_cards": [],
        "stats": {"generations": 0, "people": 0, "memories": 0, "missing": 0},
        "dashboard": None,
        "generation_sections": [],
        "generation_rows": [],
        "rows": [],
        "people": [],
        "branch_panels": [],
        "memory_rails": [],
        "memories": [],
        "recent_activities": [],
        "top_achievers": [],
        "generation_count": 0,
        "people_count": 0,
        "photo_count": 0,
        "story_count": 0,
        "empty_state": True,
        "is_demo_context": False,
    }


def _anchor_for_user(family, user):
    if not getattr(user, "is_authenticated", False):
        return None
    membership = family.memberships.select_related("person").filter(user=user).first()
    if membership and membership.person:
        return membership.person
    return None


def _relative_generation_rows(
    anchor,
    people_by_id,
    *,
    parents_by_child,
    children_by_parent,
    siblings_by_person,
    people_with_partners,
    children_count_by_parent,
):
    rows_by_number = {0: _people_from_ids({anchor.id, *siblings_by_person.get(anchor.id, set())}, people_by_id)}

    current_ids = {anchor.id}
    for level in range(1, MAX_HOMEPAGE_DEPTH + 1):
        parent_ids = _next_related_ids(current_ids, parents_by_child)
        if not parent_ids:
            break
        rows_by_number[-level] = _people_from_ids(parent_ids, people_by_id)
        current_ids = parent_ids

    current_ids = {anchor.id}
    for level in range(1, MAX_HOMEPAGE_DEPTH + 1):
        child_ids = _next_related_ids(current_ids, children_by_parent)
        if not child_ids:
            break
        rows_by_number[level] = _people_from_ids(child_ids, people_by_id)
        current_ids = child_ids

    rows = []
    for generation_number in sorted(rows_by_number):
        generation_people = rows_by_number[generation_number]
        if not generation_people:
            continue
        rows.append(
            {
                "number": generation_number,
                "label": _generation_label(generation_number),
                "title": _generation_title(generation_number),
                "subtitle": _generation_subtitle(generation_number),
                "people": [
                    _enrich_person(
                        person,
                        _generation_title(generation_number),
                        generation_number,
                        person.id in people_with_partners,
                        children_count_by_parent.get(person.id, 0),
                        relationship_label=_relationship_label(generation_number, person.id == anchor.id),
                    )
                    for person in generation_people
                ],
            }
        )
    return rows


def _family_relationship_maps(family, people_by_id):
    person_ids = set(people_by_id)
    parents_by_child = {person_id: set() for person_id in person_ids}
    children_by_parent = {person_id: set() for person_id in person_ids}
    siblings_by_person = {person_id: set() for person_id in person_ids}
    partners_by_person = {person_id: set() for person_id in person_ids}

    relationships = Relationship.objects.filter(
        family=family,
        from_person_id__in=person_ids,
        to_person_id__in=person_ids,
    ).values_list("from_person_id", "to_person_id", "relationship_type")

    for from_id, to_id, relationship_type in relationships:
        if relationship_type in PARENT_TREE_TYPES:
            children_by_parent[from_id].add(to_id)
            parents_by_child[to_id].add(from_id)
        elif relationship_type == Relationship.Type.SIBLING:
            siblings_by_person[from_id].add(to_id)
            siblings_by_person[to_id].add(from_id)
        elif relationship_type in PARTNER_TREE_TYPES:
            partners_by_person[from_id].add(to_id)
            partners_by_person[to_id].add(from_id)

    for child_id, parent_ids in parents_by_child.items():
        for parent_id in parent_ids:
            siblings_by_person[child_id].update(children_by_parent.get(parent_id, set()))
        siblings_by_person[child_id].discard(child_id)

    return parents_by_child, children_by_parent, siblings_by_person, partners_by_person


def _close_family_dashboard(
    anchor,
    people_by_id,
    *,
    parents_by_child,
    children_by_parent,
    siblings_by_person,
    partners_by_person,
):
    groups = [
        _close_family_group(
            "parents",
            "Parents",
            "arrow-up",
            _people_from_ids(parents_by_child.get(anchor.id, set()), people_by_id),
            "Add parent",
            "Record the people one generation above you.",
        ),
        _close_family_group(
            "partners",
            "Partner",
            "heart",
            _people_from_ids(partners_by_person.get(anchor.id, set()), people_by_id),
            "Add partner",
            "Connect your spouse or partner when you are ready.",
        ),
        _close_family_group(
            "children",
            "Children",
            "baby",
            _people_from_ids(children_by_parent.get(anchor.id, set()), people_by_id),
            "Add child",
            "Add your children below your Gen 0 profile.",
        ),
        _close_family_group(
            "siblings",
            "Siblings",
            "users",
            _people_from_ids(siblings_by_person.get(anchor.id, set()), people_by_id),
            "Add sibling",
            "Keep your own generation together.",
        ),
    ]
    missing_fields = _profile_missing_fields(anchor)
    return {
        "profile": _person_card_from_model(anchor, "Me · Gen 0"),
        "profile_completion": _profile_completion(anchor),
        "profile_missing": missing_fields,
        "profile_missing_count": len(missing_fields),
        "groups": groups,
        "quick_actions": [
            {"label": "Add parent", "icon": "arrow-up", "href": "/tree/", "kind": "primary"},
            {"label": "Add partner", "icon": "heart", "href": "/tree/", "kind": "soft"},
            {"label": "Add child", "icon": "baby", "href": "/tree/", "kind": "soft"},
            {"label": "Invite family", "icon": "send", "href": "/tree/", "kind": "soft"},
            {"label": "Add memory", "icon": "image", "href": "/memories/", "kind": "soft"},
            {"label": "Write story", "icon": "file-text", "href": "/stories/create/", "kind": "soft"},
        ],
    }


def _close_family_group(key, title, icon, people, action_label, empty_text):
    return {
        "key": key,
        "title": title,
        "icon": icon,
        "people": [_person_card_from_model(person, _close_family_role(key)) for person in people],
        "action_label": action_label,
        "action_href": "/tree/",
        "empty_text": empty_text,
    }


def _close_family_role(key):
    return {
        "parents": "Parent",
        "partners": "Partner",
        "children": "Child",
        "siblings": "Sibling",
    }.get(key, "Relative")


def _profile_missing_fields(person):
    missing = []
    if not person.first_name or person.first_name.lower().startswith("calvin2411"):
        missing.append("real first name")
    if not person.last_name or person.last_name.lower() in {"family", "tree"}:
        missing.append("real surname")
    if not person.profile_photo:
        missing.append("profile photo")
    if not person.birth_date:
        missing.append("date of birth")
    if not person.birth_place and not person.current_place:
        missing.append("place")
    if not person.biography:
        missing.append("short story")
    return missing


def _profile_completion(person):
    fields = [
        bool(person.first_name and not person.first_name.lower().startswith("calvin2411")),
        bool(person.last_name and person.last_name.lower() not in {"family", "tree"}),
        bool(person.profile_photo),
        bool(person.birth_date),
        bool(person.birth_place or person.current_place),
        bool(person.biography),
    ]
    return round(sum(fields) / len(fields) * 100)


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


def _rows_from_generation_rows(generation_rows):
    return [
        {
            "id": f"row-generation-{index}",
            "title": generation["title"],
            "subtitle": generation["subtitle"],
            "people": [_person_card_from_enriched(person) for person in generation["people"]],
            "add_action_label": "Open tree page",
        }
        for index, generation in enumerate(generation_rows, start=1)
    ]


def _generation_sections_from_rows(generation_rows):
    rows = _rows_from_generation_rows(generation_rows)
    return [
        {
            "id": f"generation-{index}",
            "label": generation["label"],
            "title": generation["title"],
            "subtitle": generation["subtitle"],
            "is_open": index <= 2,
            "rows": [rows[index - 1]],
        }
        for index, generation in enumerate(generation_rows, start=1)
    ]


def _build_branch_panels(family, person_cards):
    panels = []
    child_links = Relationship.objects.filter(
        family=family,
        relationship_type__in=PARENT_TREE_TYPES,
        from_person_id__in=person_cards,
        to_person_id__in=person_cards,
    )
    children_by_parent = {}
    for link in child_links:
        children_by_parent.setdefault(link.from_person_id, []).append(person_cards[link.to_person_id])

    partner_links = Relationship.objects.filter(
        family=family,
        relationship_type__in=PARTNER_TREE_TYPES,
        from_person_id__in=person_cards,
        to_person_id__in=person_cards,
    )
    partners_by_person = {}
    for link in partner_links:
        partners_by_person.setdefault(link.from_person_id, []).append(person_cards[link.to_person_id])
        partners_by_person.setdefault(link.to_person_id, []).append(person_cards[link.from_person_id])

    for person_id, children in children_by_parent.items():
        owner = person_cards[person_id]
        panels.append(
            {
                "id": f"branch-{person_id}",
                "title": f"{owner['name']}'s branch",
                "owner": owner,
                "spouses": partners_by_person.get(person_id, []),
                "children": children,
                "missing_actions": ["Add partner", "Add child", "Attach memory"],
            }
        )
    return panels


def _build_demo_context():
    family = {"name": "Demo Family Tree", "description": "Example data shown before you sign in.", "is_demo": True}
    alex = _person_card("demo-alex", "Alex Green", "Root person", "AG", is_direct_line=True, memory_count=2)
    maya = _person_card("demo-maya", "Maya Green", "Parent", "MG", is_direct_line=True, memory_count=1)
    noah = _person_card("demo-noah", "Noah Green", "Child", "NG", is_direct_line=True, memory_count=0)

    generation_rows = [
        {
            "number": 1,
            "label": "Gen 1",
            "title": "Founders",
            "subtitle": "Example cards only. Sign in to build your real tree.",
            "people": [_demo_enriched_person(alex, "Founder", 1), _demo_enriched_person(maya, "Founder", 1)],
        },
        {
            "number": 2,
            "label": "Gen 2",
            "title": "Children",
            "subtitle": "Example descendant row.",
            "people": [_demo_enriched_person(noah, "Child", 2)],
        },
    ]
    rows = [
        _relationship_row("Founders", "Example cards only. Sign in to build your real tree.", [alex, maya], "Start your tree"),
        _relationship_row("Children", "Example descendant row.", [noah], "Start your tree"),
    ]
    generation_sections = [
        {"id": "generation-1", "label": "Gen 1", "title": "Founders", "subtitle": "Example data shown before sign in.", "is_open": True, "rows": [rows[0]]},
        {"id": "generation-2", "label": "Gen 2", "title": "Children", "subtitle": "Example data shown before sign in.", "is_open": True, "rows": [rows[1]]},
    ]
    memory_rails = [
        _memory_rail("Photo memories", "Example memory cards.", [_memory_item("demo-memory-1", "Wedding portrait", "photo", "Linked to demo tree")]),
    ]
    return {
        "family": family,
        "root_person": alex,
        "right_panel": _right_panel(alex, family, len(generation_rows), is_demo_context=True),
        "today_cards": _demo_today_cards(),
        "stats": {"generations": len(generation_rows), "people": 3, "memories": 1, "missing": 0},
        "dashboard": None,
        "generation_sections": generation_sections,
        "generation_rows": generation_rows,
        "rows": rows,
        "people": [alex, maya, noah],
        "branch_panels": [],
        "memory_rails": memory_rails,
        "memories": [],
        "recent_activities": [],
        "top_achievers": [],
        "generation_count": len(generation_rows),
        "people_count": 3,
        "photo_count": 0,
        "story_count": 0,
        "empty_state": False,
        "is_demo_context": True,
    }


def _enrich_person(person, generation_title, generation_number, has_spouse, children_count, *, relationship_label=None):
    color_primary, color_soft = _generation_colors(generation_number)
    return {
        "id": person.id,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "full_name": person.full_name,
        "initials": _initials(person.first_name, person.last_name),
        "role": relationship_label or generation_title,
        "generation_label": _generation_label(generation_number),
        "birth_date": person.birth_date,
        "death_date": person.death_date,
        "birth_place": person.birth_place,
        "current_place": person.current_place,
        "profile_photo": person.profile_photo,
        "color1": color_primary,
        "color2": color_soft,
        "has_spouse": has_spouse,
        "children_count": children_count,
        "is_demo": False,
    }


def _demo_enriched_person(person, generation_label, generation_number):
    color_primary, color_soft = _generation_colors(generation_number)
    name_parts = person["name"].split()
    return {
        "id": person["id"],
        "first_name": name_parts[0],
        "last_name": name_parts[-1],
        "full_name": person["name"],
        "initials": person["initials"],
        "role": generation_label,
        "generation_label": _generation_label(generation_number),
        "birth_date": None,
        "death_date": None,
        "birth_place": "",
        "current_place": "",
        "profile_photo": "",
        "color1": color_primary,
        "color2": color_soft,
        "has_spouse": False,
        "children_count": person.get("memory_count", 0),
        "is_demo": True,
    }


def _generation_label(number):
    if number == 0:
        return "Gen 0"
    if number > 0:
        return f"Gen +{number}" if number <= MAX_HOMEPAGE_DEPTH else f"Gen {number}"
    return f"Gen {number}"


def _generation_title(number):
    titles = {-3: "Great-grandparents", -2: "Grandparents", -1: "Parents", 0: "My generation", 1: "Children", 2: "Grandchildren", 3: "Great-grandchildren"}
    return titles.get(number, "Relatives")


def _generation_subtitle(number):
    if number == 0:
        return "You and siblings in one independent row."
    if number < 0:
        return "Ancestors connected to your Gen 0 anchor."
    return "Descendants connected to your Gen 0 anchor."


def _relationship_label(generation_number, is_anchor):
    if is_anchor:
        return "Me"
    labels = {-2: "Grandparent", -1: "Parent", 0: "Sibling", 1: "Child", 2: "Grandchild", 3: "Great-grandchild"}
    if generation_number < -2:
        return "Ancestor"
    if generation_number > 3:
        return "Descendant"
    return labels.get(generation_number, "Relative")


def _generation_colors(generation_number):
    colors = {
        -3: ("#d97706", "#f59e0b"),
        -2: ("#d97706", "#f59e0b"),
        -1: ("#2563eb", "#3b82f6"),
        0: ("#059669", "#10b981"),
        1: ("#2563eb", "#3b82f6"),
        2: ("#059669", "#10b981"),
        3: ("#7c3aed", "#a78bfa"),
    }
    return colors.get(generation_number, ("#059669", "#10b981"))


def _person_card_from_model(person, relationship_label):
    return _person_card(
        person.id,
        person.full_name,
        relationship_label,
        _initials(person.first_name, person.last_name),
        memory_count=person.memories.count() + person.stories.count(),
        avatar_url=person.profile_photo.url if person.profile_photo else "",
        source_id=person.id,
    )


def _person_card_from_enriched(person):
    profile_photo = person.get("profile_photo")
    return _person_card(
        person["id"],
        person["full_name"],
        person["role"],
        person["initials"],
        memory_count=person.get("children_count", 0),
        avatar_url=profile_photo.url if profile_photo else "",
        source_id=person["id"],
    )


def _person_card(person_id, name, relationship_label, initials, *, is_direct_line=False, is_side_branch=False, is_spouse=False, memory_count=0, avatar_url="", source_id=None):
    badges = []
    if is_direct_line:
        badges.append("Direct")
    if is_side_branch:
        badges.append("Side branch")
    if is_spouse:
        badges.append("Spouse")
    if memory_count:
        badges.append(f"{memory_count} memories")
    return {
        "id": person_id,
        "source_id": source_id or person_id,
        "name": name,
        "relationship_label": relationship_label,
        "initials": initials,
        "avatar_url": avatar_url,
        "is_direct_line": is_direct_line,
        "is_side_branch": is_side_branch,
        "is_spouse": is_spouse,
        "memory_count": memory_count,
        "badges": badges,
        "branch_panel_id": "",
        "branch_panel": None,
    }


def _relationship_row(title, subtitle, people, add_action_label):
    return {"id": title.lower().replace(" ", "-"), "title": title, "subtitle": subtitle, "people": people, "add_action_label": add_action_label}


def _right_panel(root_person, family, generation_count, *, is_demo_context):
    if not root_person:
        return _empty_right_panel(family)
    return {
        "name": root_person["name"],
        "initials": root_person["initials"],
        "avatar_url": root_person.get("avatar_url", ""),
        "meta": "Example profile" if is_demo_context else f"{root_person['relationship_label']} • Gen 0 anchor",
        "family_hint": family["name"] if isinstance(family, dict) else family.name,
        "generation_count": generation_count,
        "is_demo": is_demo_context,
    }


def _empty_right_panel(family=None):
    family_name = family.name if family else "Your family tree"
    return {"name": "No anchor yet", "initials": "HT", "avatar_url": "", "meta": "Start from your tree page", "family_hint": family_name, "generation_count": 0, "is_demo": False}


def _today_cards_from_family(people):
    today = date.today()
    cards = []
    for person in people:
        if person.birth_date and person.birth_date.month == today.month and person.birth_date.day == today.day:
            cards.append({"icon": "cake", "title": "Family birthday", "subtitle": f"{person.full_name} — born {person.birth_date.strftime('%d %B %Y')}", "href": "/tree/", "toast": ""})
    return cards[:3]


def _demo_today_cards():
    return [
        {"icon": "cake", "title": "Family Birthday", "subtitle": "Example birthday reminder before sign in.", "href": "", "toast": "Birthday memory opened"},
        {"icon": "heart", "title": "Anniversary", "subtitle": "Example anniversary card before sign in.", "href": "", "toast": "Anniversary memory opened"},
        {"icon": "camera", "title": "Family Reunion", "subtitle": "Example reunion memory before sign in.", "href": "", "toast": "Reunion memory opened"},
    ]


def _memory_rail(title, subtitle, items):
    return {"title": title, "subtitle": subtitle, "items": items}


def _memory_item(item_id, title, memory_type, linked_label, summary="Attached to the family tree."):
    return {"id": item_id, "title": title, "memory_type": memory_type, "summary": summary, "linked_label": linked_label, "thumbnail_url": "", "linked_object_url": "#tree-canvas"}


def _memory_item_from_memory(memory):
    linked_people = list(memory.people.all()[:2])
    linked_label = ", ".join(person.full_name for person in linked_people) or "Family tree"
    return _memory_item(memory.id, memory.title, memory.memory_type, f"Linked to {linked_label}", memory.description or "A preserved memory attached to this family.")


def _memory_item_from_story(story):
    linked_people = list(story.people.all()[:2])
    linked_label = ", ".join(person.full_name for person in linked_people) or "Family tree"
    summary = story.body[:110] + ("..." if len(story.body) > 110 else "")
    return _memory_item(story.id, story.title, "story", f"Linked to {linked_label}", summary)


def _initials(first_name, last_name):
    return f"{first_name[:1]}{last_name[:1]}".upper() or "FM"
