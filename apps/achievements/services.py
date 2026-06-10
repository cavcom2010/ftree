from apps.achievements.models import Achievement, UserAchievement
from apps.people.models import Person
from apps.social.models import Activity
from apps.stories.models import Story


def award_achievement(family, user, code):
    achievement = Achievement.objects.filter(code=code).first()
    if not achievement:
        return None

    ua, created = UserAchievement.objects.get_or_create(
        family=family,
        user=user,
        achievement=achievement,
    )

    if created:
        Activity.objects.create(
            family=family,
            actor=user,
            activity_type=Activity.Type.ACHIEVEMENT_EARNED,
            message=f"Earned achievement: {achievement.name}",
        )

    return ua


def check_branch_builder(family, user):
    count = Person.objects.filter(family=family, created_by=user).count()
    if count >= 5:
        award_achievement(family, user, "branch-builder")


def check_story_teller(family, user):
    count = Story.objects.filter(family=family, author=user).count()
    if count >= 3:
        award_achievement(family, user, "story-teller")


def check_memory_keeper(family, user):
    from apps.memories.models import Memory
    count = Memory.objects.filter(family=family, uploaded_by=user).count()
    if count >= 5:
        award_achievement(family, user, "memory-keeper")
