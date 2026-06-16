import json

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.families.models import Family, FamilyMembership
from apps.families.services import can_invite, current_family_for_user
from apps.people.forms import PersonForm, PersonNameForm
from apps.people.models import Person
from apps.people.services import get_descendant_generation, get_generation_label
from apps.social.models import Activity


User = get_user_model()


def _family(request=None):
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        family_slug = None
        if request is not None:
            family_slug = request.session.get("current_family_slug")
        family = current_family_for_user(user, family_slug=family_slug)
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


def _can_edit_person(person, user):
    if not getattr(user, "is_authenticated", False):
        return False

    membership = FamilyMembership.objects.filter(family=person.family, user=user).first()
    if not membership:
        return False

    if membership.person_id == person.id:
        return True

    if membership.role in {FamilyMembership.Role.OWNER, FamilyMembership.Role.ADMIN}:
        return True

    person_is_claimed = FamilyMembership.objects.filter(family=person.family, person=person).exists()
    return can_invite(person.family, user) and not person_is_claimed


def person_drawer(request, person_id):
    person = get_object_or_404(Person, id=person_id, family=_family(request))
    context = {
        "person": person,
        "generation_label": get_generation_label(person),
        "can_edit_name": _can_edit_person(person, request.user),
    }
    if request.headers.get("HX-Request"):
        return render(request, "people/partials/person_drawer.html", context)
    return render(request, "people/person_drawer.html", context)


@login_required
def person_edit_name(request, person_id):
    person = get_object_or_404(Person, id=person_id, family=_family(request))
    if not _can_edit_person(person, request.user):
        raise PermissionDenied("You do not have permission to edit this person.")

    if request.method == "POST":
        previous_name = person.full_name
        form = PersonNameForm(request.POST, instance=person)
        if form.is_valid():
            person = form.save()
            message = f"Updated {previous_name}'s name to {person.full_name}."
            if previous_name == person.full_name:
                message = f"Checked {person.full_name}'s name."
            Activity.objects.create(
                family=person.family,
                actor=request.user,
                activity_type=Activity.Type.PERSON_ADDED,
                message=message,
                person=person,
            )
            if request.headers.get("HX-Request"):
                response = render(
                    request,
                    "people/partials/person_name_success.html",
                    {"person": person},
                )
                response["HX-Refresh"] = "true"
                return response
            return redirect("tree")
    else:
        form = PersonNameForm(instance=person)

    return render(
        request,
        "people/partials/person_name_form.html",
        {
            "person": person,
            "form": form,
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
        "people/person_form.html",
        {
            "form": form,
            "family": family,
            "title": "Add Person",
        },
    )
