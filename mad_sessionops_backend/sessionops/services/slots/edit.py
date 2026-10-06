from datetime import time

from django.db import transaction
from django.db.models import Q

from sessionops.exceptions import ConflictError, NotFound, PermissionDenied, ValidationError
from sessionops.models import Slot
from sessionops.services.academic_year.queries import current_year_q
from sessionops.services.rbac.scope import can_modify_school, get_school_or_403


@transaction.atomic
def edit_slot(
    slot_id: int,
    day_of_week: str | None,
    start_time: time | None,
    end_time: time | None,
    user,
) -> Slot:
    try:
        slot = Slot.objects.get(slot_id=slot_id, removed=False)
    except Slot.DoesNotExist:
        raise NotFound("Slot not found.")

    partner = get_school_or_403(user, slot.school_id)
    if not can_modify_school(user, partner):
        raise PermissionDenied()

    new_day = day_of_week if day_of_week is not None else slot.day_of_week
    new_start = start_time if start_time is not None else slot.start_time
    new_end = end_time if end_time is not None else slot.end_time

    if new_start >= new_end:
        raise ValidationError("start_time must be before end_time.")

    # R7: overlap check excluding self — current school-year only (F-M10-3)
    overlapping = (
        Slot.objects.filter(
            current_year_q(),
            school_id=slot.school_id,
            day_of_week=new_day,
            is_active=True,
            removed=False,
        )
        .exclude(slot_id=slot_id)
        .filter(Q(start_time__lt=new_end) & Q(end_time__gt=new_start))
        .first()
    )
    if overlapping:
        raise ConflictError(
            f"This time overlaps with existing slot '{overlapping.slot_name}' "
            f"({overlapping.start_time.strftime('%H:%M')}–{overlapping.end_time.strftime('%H:%M')})."
        )

    slot.day_of_week = new_day
    slot.start_time = new_start
    slot.end_time = new_end
    slot.slot_name = f"{new_day.capitalize()} {new_start.strftime('%H:%M')}"
    slot.updated_by = user
    slot.save()
    return slot
