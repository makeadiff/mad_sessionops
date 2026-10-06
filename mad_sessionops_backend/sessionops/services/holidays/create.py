from datetime import date

from django.db import transaction
from django.db.models import Q

from sessionops.exceptions import ConflictError, PermissionDenied, ValidationError
from sessionops.models import SchoolHoliday
from sessionops.services.academic_year.queries import get_school_academic_year
from sessionops.services.holidays.queries import current_year_holidays_q
from sessionops.services.rbac.scope import can_modify_school, get_school_or_403
from sessionops.services.sessions.queries import get_active_session


@transaction.atomic
def create_holiday(school_id: int, payload: dict, user) -> SchoolHoliday:
    """
    Create a holiday for the school.

    Business rules enforced:
    - R-rbac:  user must have modify access to this school
    - R-cal-1: session must be configured for the school
    - R-val:   start_date <= end_date
    - R-cal-2: holiday must fall entirely within the session window
    - R-cal-3: no overlap with other active holidays at this school
    """
    partner = get_school_or_403(user, school_id)
    if not can_modify_school(user, partner):
        raise PermissionDenied()

    session = get_active_session(school_id)
    if not session:
        raise ValidationError(
            "Academic session is not configured. Configure the session before adding holidays."
        )

    start: date = payload["start_date"]
    end: date = payload["end_date"]

    if start > end:
        raise ValidationError("start_date must be on or before end_date.")

    if start < session.start_date or end > session.end_date:
        raise ValidationError(
            f"Holiday must fall within the session window "
            f"({session.start_date} – {session.end_date})."
        )

    exclude_id: int | None = payload.get("_exclude_id")

    # R-cal-3: overlap only with this school-year's holidays (+ legacy null rows).
    overlap_qs = SchoolHoliday.objects.filter(
        current_year_holidays_q(),
        school_id=school_id,
        is_active=True,
        removed=False,
    ).filter(Q(start_date__lte=end) & Q(end_date__gte=start))
    if exclude_id is not None:
        overlap_qs = overlap_qs.exclude(school_holiday_id=exclude_id)

    overlap = overlap_qs.first()
    if overlap:
        raise ConflictError(
            f"This holiday overlaps with an existing holiday "
            f"({overlap.start_date} – {overlap.end_date}, "
            f"'{overlap.get_holiday_reason_display_value()}'). Remove it first."
        )

    return SchoolHoliday.objects.create(
        school_id=school_id,
        # The session exists, so the school has an active school-year (F-M10-4).
        school_academic_year_id=get_school_academic_year(school_id),
        holiday_reason=payload["holiday_reason"],
        start_date=start,
        end_date=end,
        holiday_description=payload.get("holiday_description"),
        remarks=payload.get("remarks"),
        created_by=user,
    )
