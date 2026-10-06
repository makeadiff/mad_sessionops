from django.db.models import Count, Q, QuerySet

from sessionops.models import Class


def list_catalog() -> QuerySet[Class]:
    """All non-removed classes (active and inactive), in catalog order, with usage."""
    return (
        Class.objects.filter(removed=False)
        .select_related("next_class_id", "program_id")
        .annotate(
            in_use_count=Count(
                "schoolclass",
                filter=Q(schoolclass__is_active=True, schoolclass__removed=False),
            )
        )
        .order_by("sequence", "class_code")
    )


def list_open_catalog() -> QuerySet[Class]:
    """Classes that can be newly added to a school (public catalog endpoint)."""
    return (
        Class.objects.filter(is_active=True, removed=False, open_for_enrolment=True)
        .select_related("program_id")
        .order_by("sequence", "class_code")
    )
