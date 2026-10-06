from datetime import timedelta

from sessionops.exceptions import NotFound
from sessionops.services.academic_year.queries import (
    get_active_academic_year,
    get_school_academic_year,
)
from sessionops.services.rbac.scope import get_school_or_403


def get_session_defaults(school_id: int, user) -> dict:
    """
    Return session date defaults pre-computed from the school's Partner MOU dates.
    - default_start_date = mou_sign_date + 60 days (None if mou_sign_date is null)
    - default_end_date   = mou_end_date (may be None)
    - academic_year_label = the school's own active school-year label (e.g. "2026-2027")

    Raises PermissionDenied if the user cannot view this school.
    """
    # RBAC — also returns the Partner object for field access
    partner = get_school_or_403(user, school_id)

    default_start = None
    if partner.mou_sign_date:
        default_start = partner.mou_sign_date + timedelta(days=60)

    # The session is saved to the school's own school-year (F-M10-3), so label it
    # with that year; fall back to the global year for a school with none yet.
    say = get_school_academic_year(school_id)
    if say is not None:
        academic_year_label = say.academic_year_id.label
    else:
        try:
            academic_year_label = get_active_academic_year().label
        except NotFound:
            academic_year_label = "N/A"

    return {
        "default_start_date": default_start,
        "default_end_date": partner.mou_end_date,
        "academic_year_label": academic_year_label,
    }
