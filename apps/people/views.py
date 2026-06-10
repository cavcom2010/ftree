from django.shortcuts import get_object_or_404, render

from apps.people.models import Person
from apps.people.services import get_generation_label


def person_drawer(request, person_id):
    person = get_object_or_404(Person, id=person_id)
    return render(
        request,
        "people/partials/person_drawer.html",
        {
            "person": person,
            "generation_label": get_generation_label(person),
        },
    )
