from django.db.models import Prefetch

from sessionops.exceptions import PermissionDenied
from sessionops.models import (
    ChildClassSection,
    Partner,
    SchoolAcademicYear,
    Slot,
    SlotClassSection,
    SlotClassSectionVolunteer,
    User,
)
from sessionops.services.academic_year.queries import current_year_q
from sessionops.services.rbac.scope import can_view_school
from sessionops.services.slot_classes.helpers import normalize_subject_display_name

_DAY_ORDER = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def get_school_schedule(
    school_id: int,
    requesting_user: User,
    day_of_week: str | None = None,
) -> dict:
    """
    Return the full weekly schedule for a school, grouped by day.

    Raises PermissionDenied if the user cannot view this school.
    """
    from sessionops.exceptions import NotFound

    try:
        partner = Partner.objects.get(partner_id=school_id, converted=True)
    except Partner.DoesNotExist:
        raise NotFound(f"School {school_id} not found.")

    if not can_view_school(requesting_user, partner):
        raise PermissionDenied()

    say = (
        SchoolAcademicYear.objects.filter(school_id=school_id, is_active=True, removed=False)
        .select_related("academic_year_id")
        .first()
    )
    academic_year_label = say.academic_year_id.label if say else "—"

    scsv_qs = SlotClassSectionVolunteer.objects.filter(
        is_active=True,
        removed=False,
    ).select_related("volunteer_id")

    scs_qs = (
        SlotClassSection.objects.filter(is_active=True, removed=False)
        .select_related(
            "class_section_id",
            "class_section_subject_id__subject_id",
        )
        .prefetch_related(
            Prefetch("slotclasssectionvolunteer_set", queryset=scsv_qs),
        )
    )

    slots_qs = (
        Slot.objects.filter(current_year_q(), school_id=school_id, is_active=True, removed=False)
        .prefetch_related(Prefetch("slotclasssection_set", queryset=scs_qs))
        .order_by("start_time")
    )

    if day_of_week:
        slots_qs = slots_qs.filter(day_of_week=day_of_week)

    days_map: dict[str, list] = {d: [] for d in _DAY_ORDER}

    for slot in slots_qs:
        slot_classes = []
        for scs in slot.slotclasssection_set.all():
            active_children_count = ChildClassSection.objects.filter(
                class_section_id=scs.class_section_id_id,
                is_active=True,
                removed=False,
            ).count()
            slot_classes.append(
                {
                    "slot_class_section_id": scs.slot_class_section_id,
                    "section_name": scs.class_section_id.section_name,
                    "section_display_name": scs.class_section_id.section_display_name,
                    "subject_name": normalize_subject_display_name(
                        scs.class_section_subject_id.subject_id.subject_name
                    ),
                    "volunteers": [
                        {
                            "user_id": v.volunteer_id.user_id,
                            "user_display_name": v.volunteer_id.user_display_name,
                            "user_role": v.volunteer_id.user_role,
                        }
                        for v in scs.slotclasssectionvolunteer_set.all()
                    ],
                    "active_children_count": active_children_count,
                }
            )

        day = slot.day_of_week
        if day not in days_map:
            days_map[day] = []

        days_map[day].append(
            {
                "slot_id": slot.slot_id,
                "slot_name": slot.slot_name,
                "start_time": slot.start_time.strftime("%H:%M"),
                "end_time": slot.end_time.strftime("%H:%M"),
                "slot_classes": slot_classes,
            }
        )

    active_days = [day_of_week] if day_of_week else _DAY_ORDER
    return {
        "school_id": school_id,
        "school_name": partner.partner_name,
        "academic_year": academic_year_label,
        "days": [{"day_of_week": d, "slots": days_map.get(d, [])} for d in active_days],
    }
