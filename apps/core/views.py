import django
from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.text import slugify

from apps.core.homepage_context import build_homepage_context
from apps.core.tree_context import build_tree_context
from apps.families.models import Family, FamilyMembership
from apps.families.services import pending_invitations_for_user
from apps.people.models import Person


def health(request):
    db_ok = True
    db_error = None
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception as e:
        db_ok = False
        db_error = str(e)

    pending_migrations = -1
    if db_ok:
        try:
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            pending_migrations = len(plan)
        except Exception:
            pending_migrations = -1

    return JsonResponse(
        {
            "status": "healthy" if db_ok else "unhealthy",
            "database": "connected" if db_ok else f"error: {db_error}",
            "pending_migrations": pending_migrations,
            "timestamp": timezone.now().isoformat(),
            "django_version": django.get_version(),
        },
        status=200 if db_ok else 503,
    )


def home(request):
    family_slug = request.session.get("current_family_slug")
    if request.user.is_authenticated:
        if not (
            _is_global_tree_admin(request.user)
            and not _has_family_membership(request.user)
        ):
            family, _created_or_repaired = _ensure_starter_tree_for_user(
                request.user,
                family_slug=family_slug,
            )
            request.session["current_family_slug"] = family.slug
            family_slug = family.slug

    return render(
        request,
        "core/home.html",
        build_homepage_context(request.user, family_slug=family_slug),
    )


@login_required
def tree(request):
    is_global_admin = _is_global_tree_admin(request.user)
    if is_global_admin:
        explicit_family_slug = request.GET.get("family")
        if not explicit_family_slug and not _has_family_membership(request.user):
            return render(
                request, "tree/home.html", _admin_family_picker_context(request.user)
            )

        if (
            explicit_family_slug
            and not Family.objects.filter(slug=explicit_family_slug).exists()
        ):
            return render(
                request, "tree/home.html", _admin_family_picker_context(request.user)
            )

        if explicit_family_slug:
            request.session["current_family_slug"] = explicit_family_slug
            context = build_tree_context(
                request.user,
                family_slug=explicit_family_slug,
                anchor_id=_anchor_id_from_request(request),
                global_admin_view=True,
            )
            context["show_tree_onboarding"] = False
            return render(request, "tree/home.html", context)

    family_slug = request.GET.get("family") or request.session.get(
        "current_family_slug"
    )
    if request.GET.get("family"):
        request.session["current_family_slug"] = request.GET["family"]

    family, created_or_repaired = _ensure_starter_tree_for_user(
        request.user,
        family_slug=family_slug,
    )
    request.session["current_family_slug"] = family.slug

    context = build_tree_context(request.user, family_slug=family.slug)
    context["show_tree_onboarding"] = bool(
        created_or_repaired
        or (
            context.get("tree_anchor")
            and context.get("can_invite_relatives")
            and context.get("people_count", 0) <= 1
        )
    )

    return render(request, "tree/home.html", context)


def _is_global_tree_admin(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and (user.is_staff or user.is_superuser)
    )


def _has_family_membership(user):
    return FamilyMembership.objects.filter(user=user).exists()


def _anchor_id_from_request(request):
    value = request.GET.get("anchor")
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _admin_family_picker_context(user):
    families = list(
        Family.objects.annotate(people_count=Count("people")).order_by("name", "id")
    )
    return {
        "family": None,
        "tree_only": True,
        "tree_anchor": None,
        "anchor_choices": [],
        "available_families": families,
        "admin_family_choices": families,
        "admin_anchor_choices": [],
        "received_invitations": list(pending_invitations_for_user(user)[:8]),
        "can_invite_relatives": False,
        "relative_generation_rows": [],
        "person_cards": {},
        "generation_count": 0,
        "people_count": sum(family.people_count for family in families),
        "empty_state": not families,
        "needs_anchor_choice": False,
        "needs_family_choice": True,
        "needs_tree_setup": False,
        "show_tree_onboarding": False,
        "is_global_admin_view": True,
    }


@transaction.atomic
def _ensure_starter_tree_for_user(user, family_slug=None):
    membership_qs = FamilyMembership.objects.filter(user=user).select_related(
        "family", "person"
    )
    membership = None
    if family_slug:
        membership = membership_qs.filter(family__slug=family_slug).first()
    if not membership:
        membership = membership_qs.order_by("joined_at", "family__name").first()

    if not membership:
        return _create_starter_tree_for_user(user), True

    family = membership.family
    if membership.person_id:
        return family, False

    person = (
        Person.objects.filter(family=family, created_by=user)
        .order_by("birth_date", "first_name", "last_name", "id")
        .first()
    )
    if not person:
        person = _create_person_for_user(user, family)

    membership.person = person
    membership.save(update_fields=["person"])
    return family, True


@transaction.atomic
def _create_starter_tree_for_user(user):
    first_name, last_name = _person_name_for_user(user)
    family = Family.objects.create(
        name=f"{first_name}'s Family Tree",
        slug=_unique_family_slug(user),
        created_by=user,
    )
    person = Person.objects.create(
        family=family,
        first_name=first_name,
        last_name=last_name,
        created_by=user,
        is_private=True,
    )
    FamilyMembership.objects.create(
        family=family,
        user=user,
        person=person,
        role=FamilyMembership.Role.OWNER,
    )
    return family


def _create_person_for_user(user, family):
    first_name, last_name = _person_name_for_user(user)
    return Person.objects.create(
        family=family,
        first_name=first_name,
        last_name=last_name,
        created_by=user,
        is_private=True,
    )


def _person_name_for_user(user):
    display_name = user.get_full_name().strip()
    if not display_name:
        identity = user.email.split("@", 1)[0] if user.email else user.get_username()
        display_name = (
            identity.replace(".", " ")
            .replace("_", " ")
            .replace("-", " ")
            .strip()
            .title()
        )

    parts = [part for part in display_name.split() if part]
    if not parts:
        return "Me", "Family"
    if len(parts) == 1:
        return parts[0], "Family"
    return parts[0], " ".join(parts[1:])


def _unique_family_slug(user):
    base = (
        slugify(f"{user.get_username()} family tree") or f"user-{user.pk}-family-tree"
    )
    slug = base
    counter = 2
    while Family.objects.filter(slug=slug).exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def _empty_tree_context(user):
    return {
        "family": None,
        "tree_only": True,
        "tree_anchor": None,
        "anchor_choices": [],
        "available_families": [],
        "received_invitations": list(pending_invitations_for_user(user)[:8]),
        "can_invite_relatives": False,
        "relative_generation_rows": [],
        "generation_count": 0,
        "people_count": 0,
        "empty_state": True,
        "needs_anchor_choice": False,
        "needs_tree_setup": True,
        "show_tree_onboarding": False,
    }
