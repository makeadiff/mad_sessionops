"""F-M9-4: weekly timetable export rows — one row per slot-class, plus one row
per empty slot so gaps are visible.

A flat bulk query rather than get_school_schedule(), which does a per-slot-class
child count and its own permission check. Same active filters and subject
normalisation as that service, and the same slots as the Slots tab (list_slots).
"""

from collections import defaultdict

from django.db.models import Count

from sessionops.models import ChildClassSection, Slot, SlotClassSection, SlotClassSectionVolunteer
from sessionops.models.slot import DAY_ORDER, DAYS_OF_WEEK
from sessionops.services.academic_year.queries import current_year_q
from sessionops.services.slot_classes.helpers import normalize_subject_display_name

TIMETABLE_HEADER = [
    "day",
    "slot_name",
    "start_time",
    "end_time",
    "class",
    "bucket",
    "subject",
    "volunteers",
    "volunteer_count",
    "children_in_bucket",
]

_DAY_LABELS = dict(DAYS_OF_WEEK)


def school_timetable_rows(school_id: int) -> list[list]:
    """Rows ordered by day (Mon→Sun), start time, class, bucket."""
    slots = sorted(
        Slot.objects.filter(current_year_q(), school_id=school_id, is_active=True, removed=False),
        key=lambda s: (DAY_ORDER.get(s.day_of_week, 99), s.start_time, s.slot_id),
    )
    if not slots:
        return []

    slot_classes = list(
        SlotClassSection.objects.filter(
            slot_id__in=[s.slot_id for s in slots], is_active=True, removed=False
        ).select_related(
            "class_section_id__school_class_id__class_id",
            "class_section_subject_id__subject_id",
        )
    )

    volunteers: dict[int, list[str]] = defaultdict(list)
    for scs_id, name in SlotClassSectionVolunteer.objects.filter(
        slot_class_section_id__in=[s.slot_class_section_id for s in slot_classes],
        is_active=True,
        removed=False,
    ).values_list("slot_class_section_id", "volunteer_id__user_display_name"):
        volunteers[scs_id].append(name)

    children_by_section = dict(
        ChildClassSection.objects.filter(
            class_section_id__in={s.class_section_id_id for s in slot_classes},
            is_active=True,
            removed=False,
        )
        .values("class_section_id")
        .annotate(c=Count("child_class_section_id"))
        .values_list("class_section_id", "c")
    )

    by_slot: dict[int, list[list]] = defaultdict(list)
    for scs in slot_classes:
        section = scs.class_section_id
        class_name = (
            section.school_class_id.class_id.class_name if section.school_class_id else None
        )
        names = sorted(volunteers.get(scs.slot_class_section_id, []))
        by_slot[scs.slot_id_id].append(
            [
                class_name,
                section.section_display_name or section.section_name,
                normalize_subject_display_name(
                    scs.class_section_subject_id.subject_id.subject_name
                ),
                "; ".join(names),
                len(names),
                children_by_section.get(section.class_section_id, 0),
            ]
        )

    rows = []
    for slot in slots:
        head = [
            _DAY_LABELS.get(slot.day_of_week, slot.day_of_week),
            slot.slot_name,
            slot.start_time,
            slot.end_time,
        ]
        cells = sorted(by_slot.get(slot.slot_id, []), key=lambda c: (c[0] or "", c[1] or ""))
        if not cells:
            rows.append([*head, None, None, None, "", 0, None])
            continue
        rows.extend([*head, *c] for c in cells)
    return rows
