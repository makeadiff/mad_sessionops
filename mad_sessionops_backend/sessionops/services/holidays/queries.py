from datetime import date

from django.db.models import Q

from sessionops.models import SchoolHoliday
from sessionops.services.academic_year.queries import current_year_q


def current_year_holidays_q() -> Q:
    """Holidays of the school's own active school-year, plus legacy rows with no
    school-year (still visible until the school is progressed) — F-M10-4."""
    return current_year_q() | Q(school_academic_year_id__isnull=True)


def list_holidays(
    school_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[SchoolHoliday]:
    """
    Return active, non-removed holidays for the school's own active school-year
    (F-M10-4), ordered by start_date.
    Optional date window filter: returns holidays that overlap [start_date, end_date].
    """
    qs = SchoolHoliday.objects.filter(
        current_year_holidays_q(),
        school_id=school_id,
        is_active=True,
        removed=False,
    ).order_by("start_date")

    if start_date:
        qs = qs.filter(end_date__gte=start_date)
    if end_date:
        qs = qs.filter(start_date__lte=end_date)

    return list(qs)
