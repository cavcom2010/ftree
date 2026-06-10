from django.contrib.auth import get_user_model
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from apps.families.models import Family
from apps.memories.models import Memory
from apps.social.models import Activity, Comment, Reaction
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


def _reaction_counts(obj):
    if isinstance(obj, Story):
        qs = Reaction.objects.filter(story=obj)
    else:
        qs = Reaction.objects.filter(memory=obj)
    counts = (
        qs.values("reaction_type")
        .annotate(count=Count("id"))
    )
    return {r["reaction_type"]: r["count"] for r in counts}


def _user_reactions(obj, user):
    if isinstance(obj, Story):
        qs = Reaction.objects.filter(story=obj, user=user)
    else:
        qs = Reaction.objects.filter(memory=obj, user=user)
    return set(qs.values_list("reaction_type", flat=True))


def _build_reaction_bars(context):
    from django.template.loader import render_to_string
    parts = []
    for obj in context.get("feed_items", []):
        obj._counts = _reaction_counts(obj)
        obj._user_reactions = _user_reactions(obj, context.get("current_user"))
    return render_to_string(
        "social/partials/reaction_bar.html",
        context,
    )


def family_feed(request):
    family = _family()
    user = _user(request)

    activities = Activity.objects.filter(family=family).select_related(
        "actor", "person", "story", "memory"
    ).order_by("-created_at")

    stories = Story.objects.filter(family=family).order_by("-created_at")

    feed_items = []
    for act in activities:
        feed_items.append(act)

    for story in stories:
        counts = _reaction_counts(story)
        user_reacts = _user_reactions(story, user)
        story.reaction_counts = counts
        story.user_reactions = user_reacts

    comment_counts = {
        s.id: Comment.objects.filter(story=s).count()
        for s in stories
    }

    return render(
        request,
        "social/feed.html",
        {
            "family": family,
            "feed_items": feed_items,
            "stories": stories,
            "current_user": user,
            "comment_counts": comment_counts,
        },
    )


def toggle_reaction(request, content_type, object_id, reaction_type):
    user = _user(request)
    family = _family()

    if content_type == "story":
        obj = get_object_or_404(Story, id=object_id, family=family)
        lookup = {"story": obj}
    elif content_type == "memory":
        obj = get_object_or_404(Memory, id=object_id, family=family)
        lookup = {"memory": obj}
    else:
        return HttpResponse(status=400)

    existing = Reaction.objects.filter(
        user=user, reaction_type=reaction_type, **lookup
    ).first()

    if existing:
        existing.delete()
    else:
        Reaction.objects.create(
            family=family,
            user=user,
            reaction_type=reaction_type,
            **lookup,
        )

    obj.reaction_counts = _reaction_counts(obj)
    obj.user_reactions = _user_reactions(obj, user)
    obj.reaction_content_type = content_type
    obj.reaction_object_id = object_id

    return render(
        request,
        "social/partials/reaction_bar.html",
        {
            "item": obj,
            "content_type": content_type,
            "object_id": object_id,
        },
    )


def add_comment(request, content_type, object_id):
    user = _user(request)
    family = _family()

    if content_type == "story":
        obj = get_object_or_404(Story, id=object_id, family=family)
        lookup = {"story": obj}
    elif content_type == "memory":
        obj = get_object_or_404(Memory, id=object_id, family=family)
        lookup = {"memory": obj}
    else:
        return HttpResponse(status=400)

    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        if body:
            comment = Comment.objects.create(
                family=family, user=user, body=body, **lookup
            )
            Activity.objects.create(
                family=family,
                actor=user,
                activity_type=Activity.Type.COMMENT_ADDED,
                message=f"Commented on {content_type}",
                **lookup,
            )

    comments = Comment.objects.filter(family=family, **lookup).select_related("user").order_by("created_at")

    return render(
        request,
        "social/partials/comment_section.html",
        {
            "item": obj,
            "comments": comments,
            "content_type": content_type,
            "object_id": object_id,
        },
    )
