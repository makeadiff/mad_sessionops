from sessionops.models import SchoolSessionDetails


def get_active_session(school_id: int) -> SchoolSessionDetails | None:
    """
    Return the active session (term dates) for the school's own active school-year
    (F-M10-3: not the global year, so a school that hasn't been progressed keeps its
    own session). Returns None if the school has no school-year or no session.
    """
    return SchoolSessionDetails.objects.filter(
        school_id=school_id,
        school_academic_year__is_active=True,
        school_academic_year__removed=False,
        is_active=True,
        removed=False,
    ).first()
