from datetime import date

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, render

from apps.families.models import Family
from apps.prompts.models import FamilyPrompt, PromptAnswer
from apps.social.models import Activity

User = get_user_model()

DEFAULT_PROMPT = "What family memory should we preserve today?"


def _family(request=None):
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        family = Family.objects.filter(memberships__user=user).first()
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


def current_prompt(request):
    family = _family(request)
    today = date.today()
    prompt = FamilyPrompt.objects.filter(
        family=family, active_date=today
    ).first()

    if prompt:
        answers = prompt.answers.select_related("user").order_by("created_at")
    else:
        answers = []

    return render(
        request,
        "prompts/partials/current_prompt.html",
        {
            "prompt": prompt,
            "question": prompt.question if prompt else DEFAULT_PROMPT,
            "answers": answers,
        },
    )


def answer_prompt(request, prompt_id):
    prompt = get_object_or_404(FamilyPrompt, id=prompt_id, family=_family(request))
    user = _user(request)

    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        if body:
            PromptAnswer.objects.create(
                prompt=prompt,
                user=user,
                body=body,
            )

            Activity.objects.create(
                family=prompt.family,
                actor=user,
                activity_type=Activity.Type.STORY_ADDED,
                message=f"Answered today's family prompt",
            )

        answers = prompt.answers.select_related("user").order_by("created_at")
        return render(
            request,
            "prompts/partials/current_prompt.html",
            {
                "prompt": prompt,
                "question": prompt.question,
                "answers": answers,
            },
        )

    return render(
        request,
        "prompts/partials/prompt_answer_form.html",
        {
            "prompt": prompt,
        },
    )
