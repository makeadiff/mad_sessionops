"""F-M9-5: schools summary export rows — one row per school in scope.

Counts shown on the Schools page come straight from get_school_stats; the extra
columns are bulk grouped queries, so the query count is constant in the number
of schools.
"""

from django.db.models import Count, Q

from sessionops.models import Child, ClassSection, Partner, SchoolSessionDetails, Slot
from sessionops.services.academic_year.queries import current_year_q
from sessionops.services.schools.queries import get_chos_for_schools, get_school_stats

SCHOOLS_HEADER = [
    "partner_id",
    "school_name",
    "city",
    "state",
    "co_name",
    "cho_names",
    "academic_year",
    "active_children",
    "inactive_children",
    "volunteers",
    "classes",
    "buckets",
    "slots",
    "slot_classes",
    "term_start",
    "term_end",
    "mou_start_date",
    "mou_end_date",
]


def _count_by_school(qs) -> dict[int, int]:
    return dict(qs.values("school_id").annotate(c=Count("pk")).values_list("school_id", "c"))


def schools_summary_rows(partner_ids: list[int]) -> list[list]:
    """Rows in partner_ids order (export_school_ids orders by name)."""
    if not partner_ids:
        return []

    partners = {p.partner_id: p for p in Partner.objects.filter(partner_id__in=partner_ids)}
    stats = get_school_stats(partner_ids)
    inactive_children = _count_by_school(
        Child.objects.filter(school_id__in=partner_ids, is_active=False, removed=False)
    )
    buckets = _count_by_school(
        # Same scope as the Buckets tab (list_buckets_for_school), incl. legacy rows.
        ClassSection.objects.filter(
            current_year_q() | Q(school_academic_year_id__isnull=True),
            school_id__in=partner_ids,
            is_active=True,
            removed=False,
        )
    )
    slots = _count_by_school(
        Slot.objects.filter(
            current_year_q(),
            school_id__in=partner_ids,
            is_active=True,
            removed=False,
        )
    )
    # Same filter as services/sessions/queries.py::get_active_session (school's own year).
    terms = {
        school_id: (start, end)
        for school_id, start, end in SchoolSessionDetails.objects.filter(
            school_id__in=partner_ids,
            school_academic_year__is_active=True,
            school_academic_year__removed=False,
            is_active=True,
            removed=False,
        ).values_list("school_id", "start_date", "end_date")
    }
    chos = get_chos_for_schools(partner_ids)

    rows = []
    for pid in partner_ids:
        partner = partners.get(pid)
        if partner is None:
            continue
        s = stats.get(pid, {})
        term_start, term_end = terms.get(pid, (None, None))
        rows.append(
            [
                pid,
                partner.partner_name,
                partner.city,
                partner.state,
                partner.co_name,
                "; ".join(u.user_display_name for u in chos.get(pid, [])),
                s.get("academic_year_label"),
                s.get("children_count", 0),
                inactive_children.get(pid, 0),
                s.get("volunteers_count", 0),
                s.get("classes_count", 0),
                buckets.get(pid, 0),
                slots.get(pid, 0),
                s.get("assignments_count", 0),
                term_start,
                term_end,
                partner.mou_start_date,
                partner.mou_end_date,
            ]
        )
    return rows
