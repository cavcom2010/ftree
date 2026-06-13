from django.shortcuts import render

from apps.core.homepage_context import build_homepage_context, build_tree_context


def home(request):
    return render(request, "core/home.html", build_homepage_context())


def tree(request):
    return render(request, "tree/home.html", build_tree_context())
