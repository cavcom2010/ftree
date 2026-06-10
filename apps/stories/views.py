from django.contrib.auth import get_user_model
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import render

from apps.families.models import Family
from apps.social.models import Activity, Reaction
from apps.stories.forms import StoryForm
from apps.stories.models import Story

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


def _annotate_stories(stories, user):
    for s in stories:
        s.reaction_counts = _reaction_counts(s)
        s.user_reactions = _user_reactions(s, user)


def _reaction_counts(obj):
    qs = Reaction.objects.filter(story=obj)
    counts = qs.values("reaction_type").annotate(count=Count("id"))
    return {r["reaction_type"]: r["count"] for r in counts}


def _user_reactions(obj, user):
    return set(
        Reaction.objects.filter(story=obj, user=user).values_list(
            "reaction_type", flat=True
        )
    )


def story_list(request):
    family = _family()
    user = _user(request)
    stories = Story.objects.filter(family=family).order_by("-created_at")
    _annotate_stories(stories, user)
    return render(
        request,
        "stories/story_list.html",
        {"family": family, "stories": stories},
    )


def story_create(request):
    family = _family()
    user = _user(request)

    if request.method == "POST":
        form = StoryForm(request.POST)
        if form.is_valid():
            story = form.save(commit=False)
            story.family = family
            story.author = user
            story.save()

            Activity.objects.create(
                family=family,
                actor=user,
                activity_type=Activity.Type.STORY_ADDED,
                message=f"Published {story.title}",
                story=story,
            )

            return render(request, "stories/story_list.html", {
                "family": family,
                "stories": Story.objects.filter(family=family).order_by("-created_at"),
            })

        return render(
            request,
            "stories/story_form.html",
            {"form": form},
        )

    form = StoryForm()
    return render(
        request,
        "stories/story_form.html",
        {"form": form, "title": "Tell a Family Story"},
    )
