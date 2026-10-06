"""F-M9-8: ops gap report — one row per missing piece of setup.

Each gap is defined exactly as the matching tab shows it, reusing the same
helpers, so a gap in the file is visible on screen:

  SCHOOL_NO_TERM_DATES     Calendar tab: no session for the school's own year (get_active_session filter)
  SCHOOL_NO_SLOTS          Slots tab empty state (list_slots filter)
  CHILD_NO_BUCKET          Children tab: Active + "Unassigned" (annotate_current_placement)
  SLOT_CLASS_NO_VOLUNTEER  Slots tab: a slot-class with no active volunteer
  VOLUNTEER_UNASSIGNED     Volunteers tab card with no assignment (volunteer_rows_for_schools)
"""

from django.db.models import Count, Q

from sessionops.models import (
    Child,
    ChildClassSection,
    Partner,
    SchoolAcademicYear,
    SchoolSessionDetails,
    Slot,
    SlotClassSection,
)
from sessionops.services.academic_year.queries import current_year_q
from sessionops.services.children.queries import annotate_current_placement
from sessionops.services.exports.volunteers import (
    VOLUNTEERS_HEADER,
    format_assignment,
    volunteer_rows_for_schools,
)

GAP_TYPES = [
    "SCHOOL_NO_TERM_DATES",
    "SCHOOL_NO_SLOTS",
    "CHILD_NO_BUCKET",
    "SLOT_CLASS_NO_VOLUNTEER",
    "VOLUNTEER_UNASSIGNED",
]
GAPS_HEADER = [
    "school_id",
    "school_name",
    "school_city",
    "co_name",
    "gap_type",
    "entity_id",
    "entity_name",
    "detail",
]

_VCOL = {name: i for i, name in enumerate(VOLUNTEERS_HEADER)}


def gap_rows(partner_ids: list[int]) -> list[list]:
    """Rows ordered by school (as given — export_school_ids orders by name),
    then GAP_TYPES order, then entity name. Constant query count."""
    if not partner_ids:
        return []

    partners = {
        p.partner_id: p
        for p in Partner.objects.filter(partner_id__in=partner_ids).only(
            "partner_id", "partner_name", "city", "co_name"
        )
    }
    # gaps[(school_id, gap_type)] = [(entity_id, entity_name, detail), ...]
    gaps: dict[tuple[int, str], list[tuple]] = {}

    def add(school_id, gap_type, entity_id=None, entity_name=None, detail=None):
        gaps.setdefault((school_id, gap_type), []).append((entity_id, entity_name, detail))

    # Term dates and the year label come from each school's own school-year (F-M10-3).
    with_term = set(
        SchoolSessionDetails.objects.filter(
            school_id__in=partner_ids,
            school_academic_year__is_active=True,
            school_academic_year__removed=False,
            is_active=True,
            removed=False,
        ).values_list("school_id", flat=True)
    )
    year_label = dict(
        SchoolAcademicYear.objects.filter(
            school_id__in=partner_ids, is_active=True, removed=False
        ).values_list("school_id", "academic_year_id__label")
    )
    with_slots = set(
        Slot.objects.filter(
            current_year_q(),
            school_id__in=partner_ids,
            is_active=True,
            removed=False,
        ).values_list("school_id", flat=True)
    )
    for pid in partner_ids:
        if pid not in with_term:
            add(
                pid,
                "SCHOOL_NO_TERM_DATES",
                detail=f"No term dates set for {year_label.get(pid, 'the current year')}",
            )
        if pid not in with_slots:
            add(pid, "SCHOOL_NO_SLOTS", detail="No weekly slots")

    unplaced = (
        annotate_current_placement(
            Child.objects.filter(school_id__in=partner_ids, is_active=True, removed=False)
        )
        .filter(_current_section_id__isnull=True)
        .only("school_id", "child_id", "first_name", "last_name")
    )
    for child in unplaced:
        add(
            child.school_id,
            "CHILD_NO_BUCKET",
            child.child_id,
            f"{child.first_name} {child.last_name}".strip(),
            getattr(child, "current_class_name", None),
        )

    unstaffed = list(
        SlotClassSection.objects.filter(
            current_year_q("slot_id__"),
            slot_id__school_id__in=partner_ids,
            slot_id__is_active=True,
            slot_id__removed=False,
            is_active=True,
            removed=False,
        )
        .annotate(
            active_volunteers=Count(
                "slotclasssectionvolunteer",
                filter=Q(
                    slotclasssectionvolunteer__is_active=True,
                    slotclasssectionvolunteer__removed=False,
                ),
            )
        )
        .filter(active_volunteers=0)
        .select_related(
            "slot_id",
            "class_section_id__school_class_id__class_id",
            "class_section_subject_id__subject_id",
        )
    )
    children_by_section = dict(
        ChildClassSection.objects.filter(
            class_section_id__in={s.class_section_id_id for s in unstaffed},
            is_active=True,
            removed=False,
        )
        .values("class_section_id")
        .annotate(c=Count("child_class_section_id"))
        .values_list("class_section_id", "c")
    )
    for scs in unstaffed:
        n = children_by_section.get(scs.class_section_id_id, 0)
        add(
            scs.slot_id.school_id,
            "SLOT_CLASS_NO_VOLUNTEER",
            scs.slot_class_section_id,
            format_assignment(scs),
            f"{n} {'child' if n == 1 else 'children'} in bucket",
        )

    for school_id, rows in volunteer_rows_for_schools(partner_ids).items():
        for row in rows:
            if row[_VCOL["slot_class_count"]] == 0:
                add(
                    school_id,
                    "VOLUNTEER_UNASSIGNED",
                    row[_VCOL["user_id"]],
                    row[_VCOL["name"]],
                    row[_VCOL["contact"]],
                )

    out = []
    for pid in partner_ids:
        partner = partners.get(pid)
        if partner is None:
            continue
        for gap_type in GAP_TYPES:
            for entity_id, entity_name, detail in sorted(
                gaps.get((pid, gap_type), []), key=lambda g: ((g[1] or ""), g[0] or 0)
            ):
                out.append(
                    [
                        pid,
                        partner.partner_name,
                        partner.city,
                        partner.co_name,
                        gap_type,
                        entity_id,
                        entity_name,
                        detail,
                    ]
                )
    return out
