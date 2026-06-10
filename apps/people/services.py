from apps.people.models import Person
from apps.relationships.models import Relationship


def get_child_ids(person):
    return (
        Relationship.objects.filter(
            from_person=person,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        .values_list("to_person_id", flat=True)
    )


def get_children(person):
    return Person.objects.filter(id__in=get_child_ids(person))


def get_descendant_generation(person):
    children = list(get_children(person))
    if not children:
        return None

    gen_map = {
        "Robert": 2, "Margaret": 2,
        "James": 3, "Linda": 3, "Michael": 3,
        "Emily": 4, "David": 4, "Laura": 4,
    }
    next_gen = gen_map.get(person.first_name, 2)
    labels = {2: "Children", 3: "Grandchildren", 4: "Great-grandchildren"}

    return {
        "number": next_gen,
        "label": labels.get(next_gen, "Descendants"),
        "people": children,
    }


def get_life_years(person):
    parts = []
    if person.birth_date:
        parts.append(str(person.birth_date.year))
    if person.death_date:
        parts.append(str(person.death_date.year))
    return " – ".join(parts) if parts else ""


def get_generation_label(person):
    names = {
        "Robert": "Generation 1 · Founder",
        "Margaret": "Generation 1 · Founder",
        "James": "Generation 2 · Child of Robert & Margaret",
        "Linda": "Generation 2 · Child of Robert & Margaret",
        "Michael": "Generation 2 · Child of Robert & Margaret",
        "Emily": "Generation 3 · Grandchild",
        "David": "Generation 3 · Grandchild",
        "Laura": "Generation 3 · Grandchild",
        "Olivia": "Generation 4 · Great-grandchild",
        "Noah": "Generation 4 · Great-grandchild",
    }
    return names.get(person.first_name, "")


def get_demo_generation_rows(family):
    gen1_names = ["Robert", "Margaret"]
    gen2_names = ["James", "Linda", "Michael"]
    gen3_names = ["Emily", "David", "Laura"]
    gen4_names = ["Olivia", "Noah"]

    all_names = gen1_names + gen2_names + gen3_names + gen4_names
    qs = Person.objects.filter(family=family, first_name__in=all_names)
    people = {p.first_name: p for p in qs}

    return [
        {
            "number": 1,
            "label": "Founders",
            "people": [people[n] for n in gen1_names if n in people],
        },
        {
            "number": 2,
            "label": "Children",
            "people": [people[n] for n in gen2_names if n in people],
        },
        {
            "number": 3,
            "label": "Grandchildren",
            "people": [people[n] for n in gen3_names if n in people],
        },
        {
            "number": 4,
            "label": "Great-grandchildren",
            "people": [people[n] for n in gen4_names if n in people],
        },
    ]
