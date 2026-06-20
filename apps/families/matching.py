from difflib import SequenceMatcher

from django.db.models import Q

from apps.families.models import Family
from apps.people.models import Person


MIN_SUGGESTION_SCORE = 45


def similarity(left, right):
    left = (left or "").strip().lower()
    right = (right or "").strip().lower()
    if not left or not right:
        return 0
    return SequenceMatcher(None, left, right).ratio()


def confidence_label(score):
    if score >= 80:
        return "High"
    if score >= 60:
        return "Medium"
    return "Low"


def find_possible_family_matches(form_data, limit=8, include_private=False):
    form_data = form_data or {}
    families = Family.objects.all() if include_private else Family.objects.filter(
        visibility__in=[
            Family.Visibility.DISCOVERABLE,
            Family.Visibility.PUBLIC_ANCESTORS,
            Family.Visibility.PUBLIC_SHOWCASE,
        ]
    )
    queryset = _narrow_people_queryset(Person.objects.filter(family__in=families).select_related("family"), form_data)
    suggestions = []
    for person in queryset[:750]:
        score, reasons = score_person_match(person, form_data)
        if score >= MIN_SUGGESTION_SCORE:
            suggestions.append({
                "family": person.family,
                "person": person,
                "score": score,
                "confidence": confidence_label(score),
                "reasons": reasons,
                "safe_label": person.public_display_name,
            })
    suggestions.sort(key=lambda item: item["score"], reverse=True)
    return suggestions[:limit]


def score_person_match(person, data):
    score = 0
    reasons = []
    if similarity(person.first_name, data.get("first_name")) >= 0.9:
        score += 20
        reasons.append("first name match")
    if similarity(person.last_name, data.get("last_name")) >= 0.9:
        score += 25
        reasons.append("surname match")
    if similarity(person.middle_name, data.get("middle_name")) >= 0.85:
        score += 8
        reasons.append("middle name match")
    if data.get("maiden_name") and similarity(person.maiden_name, data.get("maiden_name")) >= 0.85:
        score += 18
        reasons.append("previous surname match")
    if person.birth_date and data.get("birth_date"):
        if person.birth_date == data["birth_date"]:
            score += 35
            reasons.append("birth date match")
        elif person.birth_date.year == data["birth_date"].year:
            score += 10
            reasons.append("birth year match")
    score += _clue_score(person, data)
    return score, reasons


def _clue_score(person, data):
    score = 0
    parent_clue = data.get("parent_clue") or ""
    if parent_clue and _relative_name_score(person.get_parents(), parent_clue) >= 0.8:
        score += 18
    region_clue = (data.get("region_clue") or "").strip().lower()
    if region_clue:
        family_regions = " ".join(str(value) for value in (person.family.regions or [])).lower()
        person_places = f"{person.birth_place} {person.current_place}".lower()
        if region_clue in family_regions or region_clue in person_places:
            score += 10
    return score


def _narrow_people_queryset(queryset, data):
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    previous_name = (data.get("maiden_name") or "").strip()
    birth_date = data.get("birth_date")
    filters = Q()
    if last_name:
        filters |= Q(last_name__istartswith=last_name[:3]) | Q(family__main_surnames__icontains=last_name)
    if previous_name:
        filters |= Q(maiden_name__istartswith=previous_name[:3]) | Q(family__maiden_surnames__icontains=previous_name)
    if first_name:
        filters |= Q(first_name__istartswith=first_name[:2])
    if birth_date:
        filters |= Q(birth_date=birth_date)
    if filters:
        queryset = queryset.filter(filters)
    return queryset.order_by("family__name", "last_name", "first_name", "id").distinct()


def _relative_name_score(relatives, clue):
    scores = [similarity(relative.full_name, clue) for relative in relatives]
    return max(scores) if scores else 0
