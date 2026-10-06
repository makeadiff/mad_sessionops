from collections import defaultdict

from django.db.models import Count, Q, QuerySet

from sessionops.exceptions import NotFound
from sessionops.models import (
    Child,
    PartnerWorknode,
    SchoolAcademicYear,
    SchoolClass,
    SlotClassSection,
    User,
)
from sessionops.services.academic_year.queries import current_year_q, get_active_academic_year
from sessionops.services.auth.role_helpers import parse_user_roles


def get_active_academic_year_label() -> str | None:
    """Label of the single globally-active academic year, or None if unconfigured."""
    try:
        return get_active_academic_year().label
    except NotFound:
        return None


def filter_schools_by_search(qs: QuerySet, search: str | None) -> QuerySet:
    """Narrow a Partner queryset by the Schools-list search box: name, city or
    state (case-insensitive contains). Shared by list_schools and the M9
    exports so a CSV covers exactly the schools shown for the same search."""
    search = (search or "").strip()
    if not search:
        return qs
    return qs.filter(
        Q(partner_name__icontains=search) | Q(city__icontains=search) | Q(state__icontains=search)
    ).distinct()


def get_school_stats(partner_ids: list[int]) -> dict[int, dict]:
    """
    Bulk-compute per-school stats for the schools list/detail views.

    volunteers_count mirrors the Volunteers tab's own matching
    (services/volunteers/list.py): active Users whose worknode_id appears in
    this school's PartnerWorknode mapping, with no further per-school
    narrowing. A worknode_id shared by more than one school (same CHO/chapter)
    therefore counts the same volunteers for each of those schools —
    intentional, kept consistent with the tab rather than de-duplicated via
    SchoolVolunteer.
    """
    if not partner_ids:
        return {}

    classes_by_school = dict(
        SchoolClass.objects.filter(
            current_year_q(), school_id__in=partner_ids, is_active=True, removed=False
        )
        .values("school_id")
        .annotate(c=Count("school_class_id"))
        .values_list("school_id", "c")
    )

    children_by_school = dict(
        Child.objects.filter(school_id__in=partner_ids, is_active=True, removed=False)
        .values("school_id")
        .annotate(c=Count("child_id"))
        .values_list("school_id", "c")
    )

    worknodes_by_school = defaultdict(set)
    for partner_id_str, worknode_id in PartnerWorknode.objects.filter(
        partner_id__in=[str(pid) for pid in partner_ids]
    ).values_list("partner_id", "worknode_id"):
        worknodes_by_school[partner_id_str].add(worknode_id)

    all_worknode_ids = {wid for wids in worknodes_by_school.values() for wid in wids}
    active_users_by_worknode = dict(
        User.objects.filter(worknode_id__in=all_worknode_ids, is_active=True)
        .values("worknode_id")
        .annotate(c=Count("user_id"))
        .values_list("worknode_id", "c")
    )

    # Label reflects the school's own active SchoolAcademicYear row, regardless of
    # whether the AcademicYear it points to is the current globally-active one —
    # a school can be mid-progression on a year that's no longer the active one.
    academic_year_by_school = dict(
        SchoolAcademicYear.objects.filter(
            school_id__in=partner_ids,
            is_active=True,
            removed=False,
            academic_year_id__removed=False,
        ).values_list("school_id", "academic_year_id__label")
    )

    # "Teaching sessions" = active SlotClassSection rows for the school (a slot
    # actually teaching a section's subject), not raw Slot rows — active year only.
    sessions_by_school = dict(
        SlotClassSection.objects.filter(
            current_year_q("slot_id__"),
            slot_id__school_id__in=partner_ids,
            is_active=True,
            removed=False,
        )
        .values("slot_id__school_id")
        .annotate(c=Count("slot_class_section_id"))
        .values_list("slot_id__school_id", "c")
    )

    stats = {}
    for pid in partner_ids:
        wids = worknodes_by_school.get(str(pid), ())
        stats[pid] = {
            "classes_count": classes_by_school.get(pid, 0),
            "children_count": children_by_school.get(pid, 0),
            "volunteers_count": sum(active_users_by_worknode.get(wid, 0) for wid in wids),
            "academic_year_label": academic_year_by_school.get(pid),
            "assignments_count": sessions_by_school.get(pid, 0),
        }
    return stats


def get_active_volunteers_count(partner_ids: list[int]) -> int:
    """Distinct count of active Users tagged to any Worknode among the given schools."""
    if not partner_ids:
        return 0
    worknode_ids = list(
        PartnerWorknode.objects.filter(partner_id__in=[str(pid) for pid in partner_ids])
        .values_list("worknode_id", flat=True)
        .distinct()
    )
    return User.objects.filter(worknode_id__in=worknode_ids, is_active=True).distinct().count()


def get_chos_for_schools(partner_ids: list[int]) -> dict[int, list[User]]:
    """
    Bulk form of get_chos_for_school: {partner_id: [CHO users]} in two queries.

    Active Users with the CHO role whose worknode_id maps to the school via
    PartnerWorknode — same worknode-matching pattern as CHO scope resolution
    (rbac/scope.py) and the Volunteers tab (services/volunteers/list.py). CHOs
    have platform access like a CO, but a chapter can have more than one, so
    each school gets a list rather than a single name like Partner.co_name.

    user_role is a comma-separated multi-role string (see role_helpers), so the
    role check is done in Python via parse_user_roles rather than an exact-match
    filter, matching how CHO scope itself is classified in rbac/scope.py.
    """
    if not partner_ids:
        return {}
    worknodes_by_school: dict[int, set[int]] = defaultdict(set)
    for partner_id, worknode_id in PartnerWorknode.objects.filter(
        partner_id__in=[str(pid) for pid in partner_ids]
    ).values_list("partner_id", "worknode_id"):
        worknodes_by_school[int(partner_id)].add(worknode_id)

    all_worknodes = {w for wids in worknodes_by_school.values() for w in wids}
    chos = [
        u
        for u in User.objects.filter(worknode_id__in=all_worknodes, is_active=True).order_by(
            "user_display_name"
        )
        if "CHO" in parse_user_roles(u.user_role)
    ]
    return {
        pid: [u for u in chos if u.worknode_id in worknodes_by_school.get(pid, ())]
        for pid in partner_ids
    }


def get_chos_for_school(school_id: int) -> list[User]:
    """CHO users for one school — see get_chos_for_schools."""
    return get_chos_for_schools([school_id]).get(school_id, [])
