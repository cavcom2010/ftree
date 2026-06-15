from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from apps.families.models import Family, FamilyMembership
from apps.families.services import can_invite, current_family_for_user
from apps.people.forms import PersonNameForm
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
    return render(
        request,
        "people/partials/person_drawer.html",
        {
            "person": person,
            "generation_label": get_generation_label(person),
            "can_edit_name": _can_edit_person(person, request.user),
        },
    )


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


@login_required
def person_create(request):
    """Legacy route kept for old links.

    Family-tree people should be created through the /tree person-card relationship
    flow so every new person is connected as a parent, partner, child, or sibling.
    A standalone create page can create orphan records that do not appear in the
    visual tree, so it now sends users back to the tree instead.
    """
    return redirect("tree")
