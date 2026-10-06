"""F-M9-3 / F-M9-7: volunteer roster export rows.

Volunteer matching mirrors services/volunteers/list.py (PartnerWorknode →
User.worknode_id, active users). Built for many schools at once in a fixed
number of queries so F-M9-7 can reuse it.
"""

from collections import defaultdict

from sessionops.models import Partner, PartnerWorknode, SlotClassSectionVolunteer, User
from sessionops.models.slot import DAY_ORDER, DAYS_OF_WEEK
from sessionops.services.academic_year.queries import current_year_q
from sessionops.services.slot_classes.helpers import normalize_subject_display_name

VOLUNTEERS_HEADER = [
    "user_id",
    "name",
    "email",
    "contact",
    "role",
    "city",
    "slot_class_count",
    "assignments",
]

# "school_city", not "city": the roster already has the volunteer's own city column.
ALL_VOLUNTEERS_HEADER = ["school_id", "school_name", "school_city", *VOLUNTEERS_HEADER]

_DAY_LABELS = dict(DAYS_OF_WEEK)


def format_assignment(scs) -> str:
    """'Monday 10:00-11:00 · 5th · Group A · English' (class omitted for classless buckets)."""
    slot = scs.slot_id
    section = scs.class_section_id
    parts = [
        f"{_DAY_LABELS.get(slot.day_of_week, slot.day_of_week)} "
        f"{slot.start_time:%H:%M}-{slot.end_time:%H:%M}"
    ]
    if section.school_class_id is not None:
        parts.append(section.school_class_id.class_id.class_name)
    parts.append(section.section_display_name or section.section_name)
    parts.append(
        normalize_subject_display_name(scs.class_section_subject_id.subject_id.subject_name)
    )
    return " · ".join(parts)


def volunteer_rows_for_schools(school_ids: list[int]) -> dict[int, list[list]]:
    """{school_id: rows} — one row per (school, volunteer), ordered by volunteer name."""
    if not school_ids:
        return {}

    worknodes_by_school: dict[int, set[int]] = defaultdict(set)
    for partner_id, worknode_id in PartnerWorknode.objects.filter(
        partner_id__in=[str(sid) for sid in school_ids]
    ).values_list("partner_id", "worknode_id"):
        if worknode_id is not None:
            worknodes_by_school[int(partner_id)].add(worknode_id)

    all_worknodes = {w for wids in worknodes_by_school.values() for w in wids}
    users = list(
        User.objects.filter(worknode_id__in=all_worknodes, is_active=True).order_by(
            "user_display_name", "user_id"
        )
    )

    # Active assignments on active slot-classes/slots at these schools, grouped
    # by (school, volunteer). The tab filters only the assignment row + school;
    # the extra active checks guard legacy data (the M3 delete cascade already
    # soft-deletes assignment rows).
    assignments: dict[tuple[int, int], list] = defaultdict(list)
    scsv_qs = SlotClassSectionVolunteer.objects.filter(
        current_year_q("slot_class_section_id__slot_id__"),
        is_active=True,
        removed=False,
        volunteer_id__in=[u.user_id for u in users],
        slot_class_section_id__is_active=True,
        slot_class_section_id__removed=False,
        slot_class_section_id__slot_id__is_active=True,
        slot_class_section_id__slot_id__removed=False,
        slot_class_section_id__slot_id__school_id__in=school_ids,
    ).select_related(
        "slot_class_section_id__slot_id",
        "slot_class_section_id__class_section_id__school_class_id__class_id",
        "slot_class_section_id__class_section_subject_id__subject_id",
    )
    for scsv in scsv_qs:
        scs = scsv.slot_class_section_id
        assignments[(scs.slot_id.school_id, scsv.volunteer_id_id)].append(scs)

    rows: dict[int, list[list]] = {}
    for school_id in school_ids:
        wids = worknodes_by_school.get(school_id)
        if not wids:
            continue
        school_rows = []
        for user in users:
            if user.worknode_id not in wids:
                continue
            scs_list = sorted(
                assignments.get((school_id, user.user_id), []),
                key=lambda s: (
                    DAY_ORDER.get(s.slot_id.day_of_week, 99),
                    s.slot_id.start_time,
                ),
            )
            texts = [format_assignment(s) for s in scs_list]
            school_rows.append(
                [
                    user.user_id,
                    user.user_display_name,
                    user.email or user.user_login,
                    user.contact,
                    user.user_role,
                    user.city,
                    len(texts),
                    "; ".join(texts),
                ]
            )
        rows[school_id] = school_rows
    return rows


def school_volunteer_rows(school_id: int) -> list[list]:
    """Rows for one school's Volunteers-tab export."""
    return volunteer_rows_for_schools([school_id]).get(school_id, [])


def all_volunteer_rows(partner_ids: list[int]) -> list[list]:
    """F-M9-7: one row per (school, volunteer) across the given schools, in the
    given school order (export_school_ids orders by name). A volunteer on a
    worknode shared by several schools appears under each, listing only that
    school's assignments — same as each school's Volunteers tab."""
    if not partner_ids:
        return []
    schools = {
        p.partner_id: p
        for p in Partner.objects.filter(partner_id__in=partner_ids).only(
            "partner_id", "partner_name", "city"
        )
    }
    by_school = volunteer_rows_for_schools(partner_ids)
    return [
        [pid, schools[pid].partner_name, schools[pid].city, *row]
        for pid in partner_ids
        if pid in schools
        for row in by_school.get(pid, [])
    ]
