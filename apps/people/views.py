from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string

from apps.families.models import Family
from apps.people.forms import PersonForm
from apps.people.models import Person
from apps.people.services import get_descendant_generation, get_generation_label
from apps.social.models import Activity


User = get_user_model()


def _family():
    return Family.objects.first()


def _user(request):
    try:
        if request.user.is_authenticated:
            return request.user
    except AttributeError:
        pass
    return User.objects.first()


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


def person_descendants(request, person_id):
    person = get_object_or_404(Person, id=person_id)
    generation = get_descendant_generation(person)
    return render(
        request,
        "people/partials/descendant_generation.html",
        {
            "person": person,
            "generation": generation,
        },
    )


def person_create(request):
    if request.method == "POST":
        form = PersonForm(request.POST)
        if form.is_valid():
            person = form.save(commit=False)
            person.family = _family()
            person.created_by = _user(request)
            person.save()

            Activity.objects.create(
                family=_family(),
                actor=_user(request),
                activity_type=Activity.Type.PERSON_ADDED,
                message=f"Added {person.full_name} to the family tree",
                person=person,
            )

            response = HttpResponse("")
            response["HX-Trigger"] = f'{{"showToast":"{person.full_name} added!"}}'

            extra = (
                f'<div hx-swap-oob="true" id="global-sheet" class="global-sheet"></div>'
                f'<div hx-swap-oob="true" id="sheet-overlay" class="sheet-overlay"></div>'
            )
            response.content = extra
            return response

        return render(request, "people/partials/person_form.html", {"form": form})

    form = PersonForm()
    return render(
        request,
        "people/partials/person_form.html",
        {
            "form": form,
            "title": "Add Person",
        },
    )
