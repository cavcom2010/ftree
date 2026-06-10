from django.shortcuts import render

from apps.families.models import Family
from apps.people.models import Person
from apps.stories.models import Story
from apps.social.models import Activity


def home(request):
    family = Family.objects.prefetch_related("memberships").first()

    if not family:
        return render(
            request,
            "core/home.html",
            {"empty_state": True},
        )

    context = {
        "family": family,
        "people_count": Person.objects.filter(family=family).count(),
        "generation_count": 4,
        "photo_count": 27,
        "story_count": Story.objects.filter(family=family).count(),
        "recent_activities": (
            Activity.objects.filter(family=family)
            .select_related("actor", "person")
            .order_by("-created_at")[:6]
        ),
        "featured_stories": Story.objects.filter(
            family=family, is_featured=True
        )[:3],
        "empty_state": False,
    }

    return render(request, "core/home.html", context)
