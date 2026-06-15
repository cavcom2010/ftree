from apps.families.services import current_family_for_user
from apps.memories.models import Memory
from apps.people.models import Person
from apps.people.services import get_generation_rows
from apps.relationships.models import Relationship
from apps.social.models import Activity
from apps.stories.models import Story


def build_homepage_context(user=None, family_slug=None):
    if getattr(user, "is_authenticated", False):
        family = current_family_for_user(user, family_slug=family_slug)
        if family and Person.objects.filter(family=family).exists():
            return _build_family_context(family, is_demo_context=False)
        return _build_empty_context(family)

    return _build_demo_context()


def _build_family_context(family, *, is_demo_context):
    people = list(
        Person.objects.filter(family=family)
        .prefetch_related("memories", "stories")
        .order_by("birth_date", "first_name", "last_name", "id")
    )
    if not people:
        return _build_empty_context(family)

    person_cards = {
        person.id: _person_card_from_model(person, "Family member")
        for person in people
    }
    root_person = people[0]
    root_card = person_cards[root_person.id]

    partner_links = Relationship.objects.filter(
        family=family,
        relationship_type__in=[
            Relationship.Type.SPOUSE,
            Relationship.Type.PARTNER,
            Relationship.Type.EX_PARTNER,
        ],
        from_person_id__in=person_cards,
    )
    people_with_partners = {link.from_person_id for link in partner_links}

    child_links = Relationship.objects.filter(
        family=family,
        relationship_type__in=[
            Relationship.Type.PARENT_CHILD,
            Relationship.Type.ADOPTIVE_PARENT,
            Relationship.Type.STEP_PARENT,
            Relationship.Type.GUARDIAN,
        ],
        from_person_id__in=person_cards,
    )
    children_count_by_parent = {}
    for link in child_links:
        children_count_by_parent[link.from_person_id] = children_count_by_parent.get(link.from_person_id, 0) + 1

    generation_rows = []
    generation_sections = []
    rows = []
    raw_generations = list(get_generation_rows(family))
    for index, generation in enumerate(raw_generations, start=1):
        enriched_people = [
            _enrich_person(
                person,
                generation["label"],
                generation["number"],
                person.id in people_with_partners,
                children_count_by_parent.get(person.id, 0),
            )
            for person in generation["people"]
        ]
        generation_rows.append(
            {
                "number": generation["number"],
                "label": generation["label"],
                "people": enriched_people,
            }
        )

        row_people = [
            person_cards[person.id]
            for person in generation["people"]
            if person.id in person_cards
        ]
        row = {
            "id": f"row-generation-{index}",
            "title": generation["label"],
            "subtitle": "Relatives grouped from recorded parent and child links.",
            "people": row_people,
            "add_action_label": "Add from tree page",
        }
        rows.append(row)
        generation_sections.append(
            {
                "id": f"generation-{index}",
                "label": f"Gen {index}",
                "title": generation["label"],
                "subtitle": "Open the row to inspect this part of the tree.",
                "is_open": index <= 2,
                "rows": [row],
            }
        )

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

    context_people = list(person_cards.values())
    photo_count = memories.filter(memory_type=Memory.Type.PHOTO).count()
    story_count = stories.count()
    return {
        "family": family,
        "root_person": root_card,
        "stats": {
            "generations": len(generation_sections),
            "people": len(context_people),
            "memories": memories.count() + stories.count(),
            "missing": 0,
        },
        "generation_sections": generation_sections,
        "generation_rows": generation_rows,
        "rows": rows,
        "people": context_people,
        "branch_panels": branch_panels,
        "memory_rails": memory_rails,
        "memories": list(memories[:6]),
        "recent_activities": list(recent_activities),
        "top_achievers": [],
        "generation_count": len(generation_sections),
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
        "stats": {"generations": 0, "people": 0, "memories": 0, "missing": 0},
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


def _build_branch_panels(family, person_cards):
    panels = []
    child_links = Relationship.objects.filter(
        family=family,
        relationship_type__in=[
            Relationship.Type.PARENT_CHILD,
            Relationship.Type.ADOPTIVE_PARENT,
            Relationship.Type.STEP_PARENT,
            Relationship.Type.GUARDIAN,
        ],
        from_person_id__in=person_cards,
        to_person_id__in=person_cards,
    )
    children_by_parent = {}
    for link in child_links:
        children_by_parent.setdefault(link.from_person_id, []).append(
            person_cards[link.to_person_id]
        )

    partner_links = Relationship.objects.filter(
        family=family,
        relationship_type__in=[
            Relationship.Type.SPOUSE,
            Relationship.Type.PARTNER,
            Relationship.Type.EX_PARTNER,
        ],
        from_person_id__in=person_cards,
        to_person_id__in=person_cards,
    )
    partners_by_person = {}
    for link in partner_links:
        partners_by_person.setdefault(link.from_person_id, []).append(
            person_cards[link.to_person_id]
        )

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
    family = {
        "name": "Demo Family Tree",
        "description": "Example data shown before you sign in.",
        "is_demo": True,
    }
    alex = _person_card("demo-alex", "Alex Green", "Root person", "AG", is_direct_line=True, memory_count=2)
    maya = _person_card("demo-maya", "Maya Green", "Parent", "MG", is_direct_line=True, memory_count=1)
    noah = _person_card("demo-noah", "Noah Green", "Child", "NG", is_direct_line=True, memory_count=0)

    generation_rows = [
        {
            "number": 1,
            "label": "Founders",
            "people": [
                _demo_enriched_person(alex, "Founder", 1),
                _demo_enriched_person(maya, "Founder", 1),
            ],
        },
        {
            "number": 2,
            "label": "Children",
            "people": [_demo_enriched_person(noah, "Child", 2)],
        },
    ]
    rows = [
        _relationship_row("Founders", "Example cards only. Sign in to build your real tree.", [alex, maya], "Start your tree"),
        _relationship_row("Children", "Example descendant row.", [noah], "Start your tree"),
    ]
    generation_sections = [
        {
            "id": "generation-1",
            "label": "Gen 1",
            "title": "Founders",
            "subtitle": "Example data shown before sign in.",
            "is_open": True,
            "rows": [rows[0]],
        },
        {
            "id": "generation-2",
            "label": "Gen 2",
            "title": "Children",
            "subtitle": "Example data shown before sign in.",
            "is_open": True,
            "rows": [rows[1]],
        },
    ]
    memory_rails = [
        _memory_rail("Photo memories", "Example memory cards.", [_memory_item("demo-memory-1", "Wedding portrait", "photo", "Linked to demo tree")]),
    ]
    return {
        "family": family,
        "root_person": alex,
        "stats": {"generations": len(generation_rows), "people": 3, "memories": 1, "missing": 0},
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


def _enrich_person(person, generation_label, generation_number, has_spouse, children_count):
    color_primary, color_soft = _generation_colors(generation_number)
    return {
        "id": person.id,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "full_name": person.full_name,
        "initials": _initials(person.first_name, person.last_name),
        "role": generation_label,
        "generation_label": generation_label,
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
        "generation_label": generation_label,
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


def _generation_colors(generation_number):
    colors = {
        1: ("#d97706", "#f59e0b"),
        2: ("#2563eb", "#3b82f6"),
        3: ("#059669", "#10b981"),
        4: ("#7c3aed", "#a78bfa"),
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


def _person_card(
    person_id,
    name,
    relationship_label,
    initials,
    *,
    is_direct_line=False,
    is_side_branch=False,
    is_spouse=False,
    memory_count=0,
    avatar_url="",
    source_id=None,
):
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
    return {
        "id": title.lower().replace(" ", "-"),
        "title": title,
        "subtitle": subtitle,
        "people": people,
        "add_action_label": add_action_label,
    }


def _memory_rail(title, subtitle, items):
    return {
        "title": title,
        "subtitle": subtitle,
        "items": items,
    }


def _memory_item(item_id, title, memory_type, linked_label, summary="Attached to the family tree."):
    return {
        "id": item_id,
        "title": title,
        "memory_type": memory_type,
        "summary": summary,
        "linked_label": linked_label,
        "thumbnail_url": "",
        "linked_object_url": "#tree-canvas",
    }


def _memory_item_from_memory(memory):
    linked_people = list(memory.people.all()[:2])
    linked_label = ", ".join(person.full_name for person in linked_people) or "Family tree"
    return _memory_item(
        memory.id,
        memory.title,
        memory.memory_type,
        f"Linked to {linked_label}",
        memory.description or "A preserved memory attached to this family.",
    )


def _memory_item_from_story(story):
    linked_people = list(story.people.all()[:2])
    linked_label = ", ".join(person.full_name for person in linked_people) or "Family tree"
    summary = story.body[:110] + ("..." if len(story.body) > 110 else "")
    return _memory_item(
        story.id,
        story.title,
        "story",
        f"Linked to {linked_label}",
        summary,
    )


def _initials(first_name, last_name):
    return f"{first_name[:1]}{last_name[:1]}".upper() or "FM"
