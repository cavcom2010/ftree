from apps.people.models import Person
from apps.relationships.models import Relationship

GENERATION_LABELS = {
    1: "Founders",
    2: "Children",
    3: "Grandchildren",
    4: "Great-grandchildren",
}


def _person_order(person):
    return (
        person.birth_date is None,
        person.birth_date or "",
        person.first_name.lower(),
        person.last_name.lower(),
        person.id,
    )


def get_child_ids(person):
    return (
        Relationship.objects.filter(
            family=person.family,
            from_person=person,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        .values_list("to_person_id", flat=True)
    )


def get_children(person):
    return Person.objects.filter(id__in=get_child_ids(person))


def get_generation_rows(family):
    people = list(Person.objects.filter(family=family))
    people_by_id = {person.id: person for person in people}
    person_ids = set(people_by_id)

    parent_child_relationships = (
        Relationship.objects.filter(
            family=family,
            relationship_type=Relationship.Type.PARENT_CHILD,
            from_person_id__in=person_ids,
            to_person_id__in=person_ids,
        )
        .values_list("from_person_id", "to_person_id")
    )

    child_ids = set()
    children_by_parent_id = {}
    for parent_id, child_id in parent_child_relationships:
        child_ids.add(child_id)
        children_by_parent_id.setdefault(parent_id, set()).add(child_id)

    current_generation = sorted(
        (person for person in people if person.id not in child_ids),
        key=_person_order,
    )
    visited_ids = set()
    rows = []
    generation_number = 1

    while current_generation:
        row_people = [
            person for person in current_generation if person.id not in visited_ids
        ]
        if not row_people:
            break

        rows.append(
            {
                "number": generation_number,
                "label": GENERATION_LABELS.get(generation_number, "Descendants"),
                "people": row_people,
            }
        )
        visited_ids.update(person.id for person in row_people)

        next_child_ids = set()
        for person in row_people:
            next_child_ids.update(children_by_parent_id.get(person.id, set()))

        current_generation = sorted(
            (
                people_by_id[child_id]
                for child_id in next_child_ids
                if child_id in people_by_id and child_id not in visited_ids
            ),
            key=_person_order,
        )
        generation_number += 1

    return rows


def get_descendant_generation(person):
    children = list(get_children(person))
    if not children:
        return None

    return {
        "number": None,
        "label": "Children",
        "people": sorted(children, key=_person_order),
    }


def get_life_years(person):
    parts = []
    if person.birth_date:
        parts.append(str(person.birth_date.year))
    if person.death_date:
        parts.append(str(person.death_date.year))
    return " – ".join(parts) if parts else ""


def get_generation_label(person):
    has_parent = Relationship.objects.filter(
        family=person.family,
        to_person=person,
        relationship_type=Relationship.Type.PARENT_CHILD,
    ).exists()
    return "Descendant" if has_parent else "Founder"
