from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string

from apps.families.models import Family
from apps.people.forms import PersonForm
from apps.people.models import Person
from apps.people.services import get_descendant_generation
from apps.relationships.models import Relationship
from apps.social.models import Activity

User = get_user_model()

RELATION_LABELS = {
    "parent": "Parent",
    "child": "Child",
    "spouse": "Spouse",
    "sibling": "Sibling",
}


def _family():
    return Family.objects.first()


def _user(request):
    try:
        if request.user.is_authenticated:
            return request.user
    except AttributeError:
        pass
    return User.objects.first()


def add_relative(request, person_id, relation_type):
    current_person = get_object_or_404(Person, id=person_id)

    if relation_type not in RELATION_LABELS:
        relation_type = "child"

    if request.method == "POST":
        form = PersonForm(request.POST)
        if form.is_valid():
            relative = form.save(commit=False)
            relative.family = _family()
            relative.created_by = _user(request)
            relative.save()

            family = _family()

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
                actor=_user(request),
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
            response["HX-Trigger"] = f'{{"showToast":"{msg}"}}'

            close = (
                f'<div hx-swap-oob="true" id="person-drawer" class="person-drawer"></div>'
                f'<div hx-swap-oob="true" id="drawer-overlay" class="drawer-overlay"></div>'
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
