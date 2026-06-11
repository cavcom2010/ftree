import json

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string

from apps.families.models import Family
from apps.people.forms import PersonForm
from apps.people.models import Person
from apps.people.services import get_descendant_generation
from apps.relationships.models import Relationship
from apps.relationships.services import find_relationship_path
from apps.social.models import Activity

User = get_user_model()

RELATION_LABELS = {
    "parent": "Parent",
    "child": "Child",
    "spouse": "Spouse",
    "sibling": "Sibling",
}


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


def add_relative(request, person_id, relation_type):
    family = _family(request)
    user = _user(request)
    current_person = get_object_or_404(Person, id=person_id, family=family)

    if relation_type not in RELATION_LABELS:
        relation_type = "child"

    if request.method == "POST":
        form = PersonForm(request.POST)
        if form.is_valid():
            relative = form.save(commit=False)
            relative.family = family
            relative.created_by = user
            relative.save()

            if relation_type == "child":
                Relationship.objects.create(
                    family=family,
                    from_person=current_person,
                    to_person=relative,
                    relationship_type=Relationship.Type.PARENT_CHILD,
                )
                msg = f"Added {relative.full_name} as child of {current_person.first_name}"

            elif relation_type == "parent":
                Relationship.objects.create(
                    family=family,
                    from_person=relative,
                    to_person=current_person,
                    relationship_type=Relationship.Type.PARENT_CHILD,
                )
                msg = f"Added {relative.full_name} as parent of {current_person.first_name}"

            elif relation_type == "spouse":
                Relationship.objects.create(
                    family=family,
                    from_person=current_person,
                    to_person=relative,
                    relationship_type=Relationship.Type.SPOUSE,
                )
                msg = f"Added {relative.full_name} as spouse of {current_person.first_name}"

            elif relation_type == "sibling":
                Relationship.objects.create(
                    family=family,
                    from_person=current_person,
                    to_person=relative,
                    relationship_type=Relationship.Type.SIBLING,
                )
                msg = f"Added {relative.full_name} as sibling of {current_person.first_name}"

            else:
                msg = f"Added {relative.full_name}"

            Activity.objects.create(
                family=family,
                actor=user,
                activity_type=Activity.Type.PERSON_ADDED,
                message=msg,
                person=relative,
            )

            descendants_html = render_to_string(
                "people/partials/descendant_generation.html",
                {
                    "person": current_person,
                    "generation": get_descendant_generation(current_person),
                },
                request=request,
            )

            response = HttpResponse("")
            response["HX-Trigger"] = json.dumps({"showToast": msg})

            close = (
                f'<div hx-swap-oob="true" id="personDrawer" class="person-drawer"></div>'
                f'<div hx-swap-oob="true" id="descendants-for-{current_person.id}">'
                f"{descendants_html}"
                f"</div>"
            )
            response.content = close
            return response

        return render(
            request,
            "relationships/partials/add_relative_form.html",
            {
                "form": form,
                "current_person": current_person,
                "relation_type": relation_type,
                "relation_label": RELATION_LABELS[relation_type],
            },
        )

    form = PersonForm()
    return render(
        request,
        "relationships/partials/add_relative_form.html",
        {
            "form": form,
            "current_person": current_person,
            "relation_type": relation_type,
            "relation_label": RELATION_LABELS[relation_type],
        },
    )


def relationship_finder(request):
    family = _family(request)
    people = Person.objects.filter(family=family).order_by("first_name")

    if request.method == "POST":
        from_id = request.POST.get("from_person")
        to_id = request.POST.get("to_person")

        person_a = None
        person_b = None

        if from_id:
            person_a = Person.objects.filter(id=from_id, family=family).first()
        if to_id:
            person_b = Person.objects.filter(id=to_id, family=family).first()

        if person_a and person_b:
            path = find_relationship_path(person_a, person_b)

            if path:
                links = len(path) - 1
                return render(
                    request,
                    "relationships/partials/finder_result.html",
                    {
                        "path": path,
                        "person_a": person_a,
                        "person_b": person_b,
                        "link_count": links,
                    },
                )
            else:
                return render(
                    request,
                    "relationships/partials/finder_result.html",
                    {
                        "person_a": person_a,
                        "person_b": person_b,
                        "no_path": True,
                    },
                )

    return render(
        request,
        "relationships/partials/finder_form.html",
        {
            "people": people,
        },
    )
