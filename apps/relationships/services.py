from collections import deque

from apps.people.models import Person
from apps.relationships.models import Relationship


def find_relationship_path(person_a, person_b):
    if person_a.id == person_b.id:
        return [person_a]

    rels = Relationship.objects.filter(
        family=person_a.family,
    )

    graph = {}
    all_ids = set()

    for rel in rels:
        a = rel.from_person_id
        b = rel.to_person_id
        all_ids.add(a)
        all_ids.add(b)
        graph.setdefault(a, []).append(b)
        graph.setdefault(b, []).append(a)

    if person_a.id not in graph or person_b.id not in graph:
        return None

    person_map = {
        p.id: p for p in Person.objects.filter(id__in=all_ids)
    }

    queue = deque([[person_a.id]])
    visited = {person_a.id}

    while queue:
        path = queue.popleft()
        current = path[-1]

        if current == person_b.id:
            return [person_map[pid] for pid in path]

        for neighbor in graph.get(current, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])

    return None
