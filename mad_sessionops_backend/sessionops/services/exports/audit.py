from sessionops.models import ExportLog, User


def log_export(
    user: User,
    export_type: str,
    *,
    row_count: int,
    school_id: int | None = None,
    filters: dict | None = None,
    school_count: int = 1,
) -> ExportLog:
    """Record one successful export (F-M9-1). Called by the view before returning the CSV."""
    return ExportLog.objects.create(
        user_id=user,
        export_type=export_type,
        school_id=school_id,
        filters=filters or {},
        school_count=school_count,
        row_count=row_count,
    )
