from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.homepage_context import build_homepage_context
from apps.core.tree_context import build_tree_context


def home(request):
    return render(request, "core/home.html", build_homepage_context())


@login_required
def tree(request):
    family_slug = request.GET.get("family") or request.session.get("current_family_slug")
    if request.GET.get("family"):
        request.session["current_family_slug"] = request.GET["family"]

    return render(
        request,
        "tree/home.html",
        build_tree_context(request.user, family_slug=family_slug),
    )
