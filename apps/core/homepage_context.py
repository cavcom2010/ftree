from apps.families.models import Family
from apps.memories.models import Memory
from apps.people.models import Person
from apps.people.services import get_generation_rows
from apps.relationships.models import Relationship
from apps.stories.models import Story


def build_homepage_context():
    family = Family.objects.prefetch_related("people").first()
    if not family or not Person.objects.filter(family=family).exists():
        return _build_demo_context()

    return _build_family_context(family)


def _build_family_context(family):
    person_qs = Person.objects.filter(family=family).prefetch_related("memories", "stories")
    people = list(person_qs)
    person_cards = {
        person.id: _person_card_from_model(person, "Family member")
        for person in people
    }
    root_person = people[0]
    root_card = person_cards[root_person.id]

    spouse_links = Relationship.objects.filter(
        family=family,
        relationship_type=Relationship.Type.SPOUSE,
        from_person_id__in=person_cards,
    )
    people_with_spouses = {link.from_person_id for link in spouse_links}

    child_links = Relationship.objects.filter(
        family=family,
        relationship_type=Relationship.Type.PARENT_CHILD,
        from_person_id__in=person_cards,
    )
    children_count_by_parent = {}
    for link in child_links:
        children_count_by_parent[link.from_person_id] = children_count_by_parent.get(link.from_person_id, 0) + 1

    generation_rows = []
    for generation in get_generation_rows(family):
        enriched_people = [
            _enrich_person(
                person,
                generation["label"],
                generation["number"],
                person.id in people_with_spouses,
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

    generation_sections = []
    rows = []
    for index, generation in enumerate(get_generation_rows(family), start=1):
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
            "add_action_label": "Connect relative",
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
        "generation_count": len(generation_sections),
        "people_count": len(context_people),
        "photo_count": photo_count,
        "story_count": story_count,
        "empty_state": False,
    }


def _build_branch_panels(family, person_cards):
    panels = []
    child_links = Relationship.objects.filter(
        family=family,
        relationship_type=Relationship.Type.PARENT_CHILD,
        from_person_id__in=person_cards,
        to_person_id__in=person_cards,
    )
    children_by_parent = {}
    for link in child_links:
        children_by_parent.setdefault(link.from_person_id, []).append(
            person_cards[link.to_person_id]
        )

    spouse_links = Relationship.objects.filter(
        family=family,
        relationship_type=Relationship.Type.SPOUSE,
        from_person_id__in=person_cards,
        to_person_id__in=person_cards,
    )
    spouses_by_person = {}
    for link in spouse_links:
        spouses_by_person.setdefault(link.from_person_id, []).append(
            person_cards[link.to_person_id]
        )

    for person_id, children in children_by_parent.items():
        owner = person_cards[person_id]
        panels.append(
            {
                "id": f"branch-{person_id}",
                "title": f"{owner['name']}'s branch",
                "owner": owner,
                "spouses": spouses_by_person.get(person_id, []),
                "children": children,
                "missing_actions": ["Add spouse", "Invite child", "Attach memory"],
            }
        )
    return panels


def _build_demo_context():
    family = {
        "name": "Moyo Family Tree",
        "description": "A private place to map generations and preserve memories.",
        "is_demo": True,
    }

    tawanda = _person_card("demo-tawanda", "Tawanda Moyo", "Grandfather", "TM", is_direct_line=True, memory_count=8)
    rudo = _person_card("demo-rudo", "Rudo Moyo", "Grandmother", "RM", is_direct_line=True, is_spouse=True, memory_count=11)
    joseph = _person_card("demo-joseph", "Joseph Moyo", "Father", "JM", is_direct_line=True, memory_count=16)
    john = _person_card("demo-john", "John Moyo", "Uncle", "JM", is_side_branch=True, memory_count=5)
    mary = _person_card("demo-mary", "Mary Dube", "Auntie", "MD", is_side_branch=True, memory_count=7)
    nyasha = _person_card("demo-nyasha", "Nyasha Moyo", "Mother", "NM", is_spouse=True, memory_count=9)
    calvin = _person_card("demo-calvin", "Calvin Moyo", "Root person", "CM", is_direct_line=True, memory_count=14)
    tariro = _person_card("demo-tariro", "Tariro Moyo", "Sister", "TM", is_side_branch=True, memory_count=4)
    blessing = _person_card("demo-blessing", "Blessing Moyo", "Brother", "BM", is_side_branch=True, memory_count=2)
    amara = _person_card("demo-amara", "Amara Moyo", "Child", "AM", is_direct_line=True, memory_count=3)
    kai = _person_card("demo-kai", "Kai Moyo", "Grandchild", "KM", is_direct_line=True, memory_count=1)

    sarah = _person_card("demo-sarah", "Sarah Moyo", "Uncle John's spouse", "SM", is_spouse=True, memory_count=2)
    aaron = _person_card("demo-aaron", "Aaron Moyo", "Cousin", "AM", is_side_branch=True, memory_count=3)
    lisa = _person_card("demo-lisa", "Lisa Moyo", "Cousin", "LM", is_side_branch=True, memory_count=1)
    peter = _person_card("demo-peter", "Peter Dube", "Auntie Mary's spouse", "PD", is_spouse=True, memory_count=1)
    faith = _person_card("demo-faith", "Faith Dube", "Cousin", "FD", is_side_branch=True, memory_count=2)

    john_panel = _branch_panel(
        "branch-demo-john",
        "Uncle John's branch",
        john,
        spouses=[sarah],
        children=[aaron, lisa],
    )
    mary_panel = _branch_panel(
        "branch-demo-mary",
        "Auntie Mary's branch",
        mary,
        spouses=[peter],
        children=[faith],
    )
    tariro_panel = _branch_panel(
        "branch-demo-tariro",
        "Tariro's branch",
        tariro,
        spouses=[],
        children=[],
        missing_actions=["Add partner", "Add child", "Invite Tariro"],
    )

    john["branch_panel"] = john_panel
    mary["branch_panel"] = mary_panel
    tariro["branch_panel"] = tariro_panel

    generation_sections = [
        _generation_section(
            "gen-minus-2",
            "Gen -2",
            "Grandparents",
            "Grandparents couple and their children.",
            True,
            [
                _relationship_row(
                    "Grandparents couple",
                    "Direct ancestors at the top of this visible branch.",
                    [tawanda, rudo],
                    "Add grandparent",
                ),
                _relationship_row(
                    "Children of Tawanda and Rudo",
                    "Father continues the direct line. Uncle and auntie open their own branches.",
                    [joseph, john, mary],
                    "Add child",
                ),
            ],
        ),
        _generation_section(
            "gen-minus-1",
            "Gen -1",
            "Parents",
            "Direct parent generation for the selected root person.",
            True,
            [
                _relationship_row(
                    "Parents",
                    "The couple that links the root person to this branch.",
                    [joseph, nyasha],
                    "Add parent",
                )
            ],
        ),
        _generation_section(
            "gen-zero",
            "Gen 0",
            "You and siblings",
            "Root person's own generation.",
            True,
            [
                _relationship_row(
                    "You and siblings",
                    "Same parents, same generation.",
                    [calvin, tariro, blessing],
                    "Add sibling",
                )
            ],
        ),
        _generation_section(
            "gen-plus-1",
            "Gen +1",
            "Children",
            "Direct descendants below the root person.",
            False,
            [
                _relationship_row(
                    "Children",
                    "Next generation connected to the root person.",
                    [amara],
                    "Add child",
                )
            ],
        ),
        _generation_section(
            "gen-plus-2",
            "Gen +2",
            "Grandchildren",
            "Youngest visible direct-line generation.",
            False,
            [
                _relationship_row(
                    "Grandchildren",
                    "Future branch to keep connected over time.",
                    [kai],
                    "Add grandchild",
                )
            ],
        ),
    ]

    branch_panels = [john_panel, mary_panel, tariro_panel]
    rows = [row for section in generation_sections for row in section["rows"]]
    people = [
        tawanda,
        rudo,
        joseph,
        john,
        mary,
        nyasha,
        calvin,
        tariro,
        blessing,
        amara,
        kai,
        sarah,
        aaron,
        lisa,
        peter,
        faith,
    ]

    generation_rows = []
    gen_number = 1
    for section in generation_sections:
        section_people = []
        for row in section["rows"]:
            for person in row["people"]:
                color_primary, color_soft = _generation_colors(gen_number)
                section_people.append(
                    {
                        "id": person["id"],
                        "first_name": person["name"].split()[0],
                        "last_name": person["name"].split()[-1],
                        "full_name": person["name"],
                        "initials": person["initials"],
                        "role": person["relationship_label"],
                        "generation_label": section["title"],
                        "birth_date": None,
                        "death_date": None,
                        "birth_place": "",
                        "current_place": "",
                        "profile_photo": "",
                        "color1": color_primary,
                        "color2": color_soft,
                        "has_spouse": person.get("is_spouse", False),
                        "children_count": person["memory_count"],
                    }
                )
        generation_rows.append(
            {
                "number": gen_number,
                "label": section["title"],
                "people": section_people,
            }
        )
        gen_number += 1

    memory_rails = [
        _memory_rail(
            "Videos",
            "Compact clips attached to branches.",
            [
                _memory_item("demo-video-1", "Grandad's garden tour", "video", "Linked to Tawanda Moyo"),
                _memory_item("demo-video-2", "Sunday lunch blessing", "video", "Linked to Gen -1"),
            ],
        ),
        _memory_rail(
            "Photo memories",
            "Small photo cards below the tree.",
            [
                _memory_item("demo-photo-1", "Rudo's wedding portrait", "photo", "Linked to grandparents couple"),
                _memory_item("demo-photo-2", "Cousins at the river", "photo", "Linked to Uncle John's branch"),
                _memory_item("demo-photo-3", "First school day", "photo", "Linked to Amara Moyo"),
            ],
        ),
        _memory_rail(
            "Story posts",
            "Written memories tied to relatives.",
            [
                _memory_item("demo-story-1", "How the family name travelled", "story", "Linked to Moyo branch"),
                _memory_item("demo-story-2", "Auntie Mary's kitchen notes", "story", "Linked to Auntie Mary's branch"),
            ],
        ),
    ]

    photo_count = len(memory_rails[1]["items"]) if len(memory_rails) > 1 else 0
    story_count = len(memory_rails[2]["items"]) if len(memory_rails) > 2 else 0
    return {
        "family": family,
        "root_person": calvin,
        "stats": {
            "generations": len(generation_sections),
            "people": len(people),
            "memories": sum(len(rail["items"]) for rail in memory_rails),
            "missing": 6,
        },
        "generation_sections": generation_sections,
        "generation_rows": generation_rows,
        "rows": rows,
        "people": people,
        "branch_panels": branch_panels,
        "memory_rails": memory_rails,
        "generation_count": len(generation_sections),
        "people_count": len(people),
        "photo_count": photo_count,
        "story_count": story_count,
        "empty_state": False,
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


def _branch_panel(panel_id, title, owner, *, spouses, children, missing_actions=None):
    owner["branch_panel_id"] = panel_id
    return {
        "id": panel_id,
        "title": title,
        "owner": owner,
        "spouses": spouses,
        "children": children,
        "missing_actions": missing_actions or ["Add spouse", "Add child", "Attach memory"],
    }


def _generation_section(section_id, label, title, subtitle, is_open, rows):
    return {
        "id": section_id,
        "label": label,
        "title": title,
        "subtitle": subtitle,
        "is_open": is_open,
        "rows": rows,
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
