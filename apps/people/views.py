import json

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from apps.families.models import Family
from apps.people.forms import PersonForm
from apps.people.models import Person
from apps.people.services import get_descendant_generation, get_generation_label
from apps.social.models import Activity


User = get_user_model()


def _family(request=None):
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        family = Family.objects.filter(memberships__user=user).first()
        if family:
            return family
    return Family.objects.first()


def _user(request):
    try:
        if request.user.is_authenticated:
            return request.user
    except AttributeError:
        pass
    return User.objects.first()


def person_drawer(request, person_id):
    person = get_object_or_404(Person, id=person_id, family=_family(request))
    return render(
        request,
        "people/partials/person_drawer.html",
        {
            "person": person,
            "generation_label": get_generation_label(person),
        },
    )


def person_descendants(request, person_id):
    person = get_object_or_404(Person, id=person_id, family=_family(request))
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
    family = _family(request)
    user = _user(request)

    if request.method == "POST":
        if not family:
            return HttpResponse("No family configured.", status=404)

        form = PersonForm(request.POST)
        if form.is_valid():
            person = form.save(commit=False)
            person.family = family
            person.created_by = user
            person.save()

            Activity.objects.create(
                family=family,
                actor=user,
                activity_type=Activity.Type.PERSON_ADDED,
                message=f"Added {person.full_name} to the family tree",
                person=person,
            )

            from apps.achievements.services import check_branch_builder
            check_branch_builder(family, user)

            response = HttpResponse("")
            response["HX-Trigger"] = json.dumps({"showToast": f"{person.full_name} added!"})

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
