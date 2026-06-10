from apps.people.models import Person


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
