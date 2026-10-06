"""M9 CSV exports.

Per-school exports mount under /api/schools/ (guard: get_school_or_403);
cross-school exports mount under /api/exports/ (scope: export_school_ids).
Endpoints are added per feature (F-M9-2..8). View shape:
    guard → get_active_academic_year() → rows → log_export() → build_csv_response()
"""

from typing import Literal, Optional

from ninja import Router

from sessionops.schemas.auth import ErrorResponseSchema
from sessionops.services.academic_year.queries import get_active_academic_year
from sessionops.services.exports.audit import log_export
from sessionops.services.exports.children import (
    ALL_CHILDREN_HEADER,
    CHILDREN_HEADER,
    all_children_rows,
    school_children_rows,
)
from sessionops.services.exports.csv_writer import build_csv_response, export_filename
from sessionops.services.exports.gaps import GAPS_HEADER, gap_rows
from sessionops.services.exports.schools import SCHOOLS_HEADER, schools_summary_rows
from sessionops.services.exports.scope import export_school_ids
from sessionops.services.exports.timetable import TIMETABLE_HEADER, school_timetable_rows
from sessionops.services.exports.volunteers import (
    ALL_VOLUNTEERS_HEADER,
    VOLUNTEERS_HEADER,
    all_volunteer_rows,
    school_volunteer_rows,
)
from sessionops.services.rbac.scope import get_school_or_403

school_exports_router = Router(tags=["Exports"])
exports_router = Router(tags=["Exports"])


def _non_empty(filters: dict) -> dict:
    return {k: v for k, v in filters.items() if v not in (None, "", False)}


@school_exports_router.get(
    "/{school_id}/exports/children.csv",
    response={403: ErrorResponseSchema, 404: ErrorResponseSchema},
)
def export_school_children(
    request,
    school_id: int,
    status: Literal["active", "inactive", "all"] = "all",
    search: Optional[str] = None,
    class_id: Optional[int] = None,
    section_id: Optional[int] = None,
    unassigned: bool = False,
):
    """F-M9-2: Children-tab export — same filters as GET /schools/{id}/children/."""
    get_school_or_403(request.auth, school_id)
    get_active_academic_year()
    rows = school_children_rows(
        school_id,
        status=status,
        search=search,
        class_id=class_id,
        section_id=section_id,
        unassigned=unassigned,
    )
    log_export(
        request.auth,
        "school_children",
        school_id=school_id,
        filters=_non_empty(
            {
                "status": status,
                "search": search,
                "class_id": class_id,
                "section_id": section_id,
                "unassigned": unassigned,
            }
        ),
        row_count=len(rows),
    )
    return build_csv_response(export_filename("children", school_id), CHILDREN_HEADER, rows)


@school_exports_router.get(
    "/{school_id}/exports/volunteers.csv",
    response={403: ErrorResponseSchema, 404: ErrorResponseSchema},
)
def export_school_volunteers(request, school_id: int):
    """F-M9-3: Volunteers-tab export with each volunteer's current slot-class assignments."""
    get_school_or_403(request.auth, school_id)
    get_active_academic_year()
    rows = school_volunteer_rows(school_id)
    log_export(request.auth, "school_volunteers", school_id=school_id, row_count=len(rows))
    return build_csv_response(export_filename("volunteers", school_id), VOLUNTEERS_HEADER, rows)


@school_exports_router.get(
    "/{school_id}/exports/timetable.csv",
    response={403: ErrorResponseSchema, 404: ErrorResponseSchema},
)
def export_school_timetable(request, school_id: int):
    """F-M9-4: weekly timetable — one row per slot-class, one blank row per empty slot."""
    get_school_or_403(request.auth, school_id)
    get_active_academic_year()
    rows = school_timetable_rows(school_id)
    log_export(request.auth, "school_timetable", school_id=school_id, row_count=len(rows))
    return build_csv_response(export_filename("timetable", school_id), TIMETABLE_HEADER, rows)


# ── Cross-school exports (Schools page) ────────────────────────────────────────


@exports_router.get("schools.csv")
def export_schools_summary(request, search: Optional[str] = None):
    """F-M9-5: one row per school in the user's scope, narrowed like the Schools page search."""
    get_active_academic_year()
    ids = export_school_ids(request.auth, search)
    rows = schools_summary_rows(ids)
    log_export(
        request.auth,
        "schools_summary",
        school_count=len(ids),
        filters=_non_empty({"search": search}),
        row_count=len(rows),
    )
    return build_csv_response(export_filename("schools", "all"), SCHOOLS_HEADER, rows)


@exports_router.get("children.csv")
def export_all_children(
    request,
    search: Optional[str] = None,
    status: Literal["active", "inactive", "all"] = "all",
):
    """F-M9-6: children across every school in scope, narrowed like the Schools page search."""
    get_active_academic_year()
    ids = export_school_ids(request.auth, search)
    rows = all_children_rows(ids, status=status)
    log_export(
        request.auth,
        "all_children",
        school_count=len(ids),
        filters=_non_empty({"search": search, "status": status}),
        row_count=len(rows),
    )
    return build_csv_response(export_filename("children", "all"), ALL_CHILDREN_HEADER, rows)


@exports_router.get("volunteers.csv")
def export_all_volunteers(request, search: Optional[str] = None):
    """F-M9-7: volunteers + assignments across every school in scope, narrowed like the page search."""
    get_active_academic_year()
    ids = export_school_ids(request.auth, search)
    rows = all_volunteer_rows(ids)
    log_export(
        request.auth,
        "all_volunteers",
        school_count=len(ids),
        filters=_non_empty({"search": search}),
        row_count=len(rows),
    )
    return build_csv_response(export_filename("volunteers", "all"), ALL_VOLUNTEERS_HEADER, rows)


@exports_router.get("gaps.csv")
def export_gap_report(request, search: Optional[str] = None):
    """F-M9-8: missing setup across every school in scope, one row per gap."""
    get_active_academic_year()
    ids = export_school_ids(request.auth, search)
    rows = gap_rows(ids)
    log_export(
        request.auth,
        "gap_report",
        school_count=len(ids),
        filters=_non_empty({"search": search}),
        row_count=len(rows),
    )
    return build_csv_response(export_filename("gaps", "all"), GAPS_HEADER, rows)
