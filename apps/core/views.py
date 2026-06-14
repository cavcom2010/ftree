from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.homepage_context import build_homepage_context
from apps.core.tree_context import build_tree_context
from apps.families.models import FamilyMembership


def home(request):
    return render(request, "core/home.html", build_homepage_context())


@login_required
def tree(request):
    family_slug = request.GET.get("family") or request.session.get("current_family_slug")
    if request.GET.get("family"):
        request.session["current_family_slug"] = request.GET["family"]

    if not FamilyMembership.objects.filter(user=request.user).exists():
        return render(request, "tree/home.html", _empty_tree_context())

    return render(
        request,
        "tree/home.html",
        build_tree_context(request.user, family_slug=family_slug),
    )


def _empty_tree_context():
    return {
        "family": None,
        "tree_only": True,
        "tree_anchor": None,
        "anchor_choices": [],
        "available_families": [],
        "received_invitations": [],
        "can_invite_relatives": False,
        "relative_generation_rows": [],
        "generation_count": 0,
        "people_count": 0,
        "empty_state": True,
        "needs_anchor_choice": False,
    }
