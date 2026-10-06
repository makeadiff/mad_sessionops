from datetime import time

from django.db import transaction
from django.db.models import Q

from sessionops.exceptions import ConflictError, PermissionDenied, ValidationError
from sessionops.models import Slot
from sessionops.services.academic_year.queries import (
    current_year_q,
    get_or_create_school_academic_year,
)
from sessionops.services.rbac.scope import can_modify_school, get_school_or_403


@transaction.atomic
def create_slot(school_id: int, day_of_week: str, start_time: time, end_time: time, user) -> Slot:
    partner = get_school_or_403(user, school_id)
    if not can_modify_school(user, partner):
        raise PermissionDenied()

    if start_time >= end_time:
        raise ValidationError("start_time must be before end_time.")

    # R7: no overlapping slots same school same day — current school-year only (F-M10-3)
    overlapping = (
        Slot.objects.filter(
            current_year_q(),
            school_id=school_id,
            day_of_week=day_of_week,
            is_active=True,
            removed=False,
        )
        .filter(Q(start_time__lt=end_time) & Q(end_time__gt=start_time))
        .first()
    )
    if overlapping:
        raise ConflictError(
            f"This time overlaps with existing slot '{overlapping.slot_name}' "
            f"({overlapping.start_time.strftime('%H:%M')}–{overlapping.end_time.strftime('%H:%M')})."
        )

    slot_name = f"{day_of_week.capitalize()} {start_time.strftime('%H:%M')}"
    say = get_or_create_school_academic_year(school_id, user)

    return Slot.objects.create(
        school_id=school_id,
        school_academic_year_id=say,
        slot_name=slot_name,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        recurring=True,
        created_by=user,
    )


def list_slots(school_id: int, user) -> list[Slot]:
    from sessionops.models.slot import DAY_ORDER

    get_school_or_403(user, school_id)  # raises 403/404 if no access

    slots = list(
        # Active academic year only — old-year slots are not shown as current (M9 decision).
        Slot.objects.filter(
            current_year_q(), school_id=school_id, is_active=True, removed=False
        ).order_by("start_time")
    )
    slots.sort(key=lambda s: (DAY_ORDER.get(s.day_of_week, 99), s.start_time))
    return slots
