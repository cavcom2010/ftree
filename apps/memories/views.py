from django.contrib.auth import get_user_model
from django.db.models import Count
from django.shortcuts import render

from apps.families.models import Family
from apps.memories.models import Memory
from apps.social.models import Reaction

User = get_user_model()


def _user(request):
    try:
        if request.user.is_authenticated:
            return request.user
    except AttributeError:
        pass
    return User.objects.first()


def _annotate_memories(memories, user):
    for m in memories:
        m.reaction_counts = _reaction_counts(m)
        m.user_reactions = _user_reactions(m, user)


def _reaction_counts(obj):
    qs = Reaction.objects.filter(memory=obj)
    counts = qs.values("reaction_type").annotate(count=Count("id"))
    return {r["reaction_type"]: r["count"] for r in counts}


def _user_reactions(obj, user):
    return set(
        Reaction.objects.filter(memory=obj, user=user).values_list(
            "reaction_type", flat=True
        )
    )


def memory_list(request):
    family = Family.objects.first()
    user = _user(request)
    memories = Memory.objects.filter(family=family).order_by("-created_at")
    _annotate_memories(memories, user)
    return render(
        request,
        "memories/memory_list.html",
        {"family": family, "memories": memories},
    )
