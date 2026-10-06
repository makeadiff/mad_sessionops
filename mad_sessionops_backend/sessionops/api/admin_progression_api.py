"""M10 Year Progression admin API. ADMIN_ROLES only (not CXO).

F-M10-5: release. F-M10-6: eligibility, precheck, preview, child picker (each
school moves from its own year to the next — no run-wide target year). F-M10-7: runs (start, execute one school, list, detail). F-M10-8: undo
(per school, until the first new-year write).
"""

from typing import List, Optional

from ninja import Router

from sessionops.exceptions import NotFound, PermissionDenied
from sessionops.models import Partner, ProgressionRun, SchoolProgression
from sessionops.schemas.auth import ErrorResponseSchema
from sessionops.schemas.progression import (
    EligibleSchoolsOut,
    PrecheckIn,
    PrecheckOut,
    PreviewChildrenPage,
    PreviewIn,
    PreviewOut,
    RunDetailOut,
    RunOut,
    RunSchoolDetailOut,
    SchoolProgressionOut,
    StartRunIn,
)
from sessionops.services.auth.role_helpers import user_has_admin_access
from sessionops.services.progression.eligibility import eligible_schools
from sessionops.services.progression.execute import execute_school
from sessionops.services.progression.freeze import release_school
from sessionops.services.progression.precheck import precheck, preview, preview_children
from sessionops.services.progression.rowlog import summary as row_log_summary
from sessionops.services.progression.start import start_run
from sessionops.services.progression.undo import can_undo, undo_school

admin_progression_router = Router(tags=["admin-progression"])

_ERR = {400: ErrorResponseSchema, 403: ErrorResponseSchema}


def _require_admin(user) -> None:
    if not user_has_admin_access(user.user_role):
        raise PermissionDenied()


def _school_progression(run_id: int, school_id: int) -> SchoolProgression:
    try:
        return SchoolProgression.objects.get(run_id=run_id, school_id=school_id)
    except SchoolProgression.DoesNotExist:
        raise NotFound(f"School {school_id} is not part of run {run_id}.")


# ── F-M10-6: eligibility, precheck, preview ────────────────────────────────────


@admin_progression_router.get("/eligible-schools/", response={200: EligibleSchoolsOut, **_ERR})
def get_eligible_schools(request):
    """Converted schools, each with its current year and the year it would move into."""
    _require_admin(request.auth)
    return 200, eligible_schools()


@admin_progression_router.post("/precheck/", response={200: List[PrecheckOut], **_ERR})
def post_precheck(request, payload: PrecheckIn):
    _require_admin(request.auth)
    return 200, precheck(payload.school_ids)


@admin_progression_router.post("/preview/", response={200: List[PreviewOut], **_ERR})
def post_preview(request, payload: PreviewIn):
    _require_admin(request.auth)
    return 200, preview([s.model_dump() for s in payload.schools])


@admin_progression_router.get(
    "/preview/{school_id}/children/",
    response={200: PreviewChildrenPage, 403: ErrorResponseSchema},
)
def get_preview_children(
    request,
    school_id: int,
    class_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    """Active children for picking individual graduations (paginated, no DOB/contact)."""
    _require_admin(request.auth)
    return 200, preview_children(
        school_id, class_id=class_id, search=search, page=page, page_size=page_size
    )


# ── F-M10-7: runs ─────────────────────────────────────────────────────────────

_RUN_ERR = {
    403: ErrorResponseSchema,
    404: ErrorResponseSchema,
    409: ErrorResponseSchema,
}


def _run_or_404(run_id: int) -> ProgressionRun:
    try:
        return ProgressionRun.objects.select_related("started_by").get(pk=run_id)
    except ProgressionRun.DoesNotExist:
        raise NotFound(f"Run {run_id} not found.")


_SP_YEARS = (
    "from_school_academic_year_id__academic_year_id",
    "to_academic_year_id",
    "run_id__to_academic_year_id",
)


def _years(sp: SchoolProgression) -> tuple[str, str | None]:
    """(from, to) labels for one school; legacy rows fall back to the run's year."""
    to = sp.to_academic_year_id or sp.run_id.to_academic_year_id
    return sp.from_school_academic_year_id.academic_year_id.label, to.label if to else None


def _run_dict(run: ProgressionRun) -> dict:
    counts: dict = {}
    moves: dict[str, int] = {}
    for sp in run.schools.select_related(*_SP_YEARS):
        counts[sp.status] = counts.get(sp.status, 0) + 1
        frm, to = _years(sp)
        key = f"{frm} → {to}"
        moves[key] = moves.get(key, 0) + 1
    return {
        "run_id": run.run_id,
        "status": run.status,
        "year_moves": [{"label": k, "schools": n} for k, n in sorted(moves.items())],
        "started_by_name": run.started_by.user_display_name,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "cleanup": run.cleanup,
        "school_counts": counts,
    }


def _school_rows(run: ProgressionRun) -> list[dict]:
    schools = list(run.schools.select_related(*_SP_YEARS).order_by("school_progression_id"))
    names = dict(
        Partner.objects.filter(partner_id__in=[s.school_id for s in schools]).values_list(
            "partner_id", "partner_name"
        )
    )
    return [_school_dict(s, names.get(s.school_id)) for s in schools]


def _school_dict(sp: SchoolProgression, name: str | None) -> dict:
    allowed, reason = can_undo(sp) if sp.status == "completed" else (False, None)
    from_label, to_label = _years(sp)
    return {
        "from_year_label": from_label,
        "to_year_label": to_label,
        "can_undo": allowed,
        "undo_block_reason": reason,
        "school_progression_id": sp.school_progression_id,
        "run_id": sp.run_id_id,
        "school_id": sp.school_id,
        "school_name": name,
        "status": sp.status,
        "error": sp.error,
        "counts": sp.counts,
        "warnings": sp.warnings,
        "graduate_class_ids": sp.graduate_class_ids,
        "graduate_child_ids": sp.graduate_child_ids,
        "started_at": sp.started_at,
        "finished_at": sp.finished_at,
    }


@admin_progression_router.post("/runs/", response={201: RunOut, **_ERR})
def post_run(request, payload: StartRunIn):
    """Start a run: move the active year forward if needed, clean up, queue + freeze."""
    _require_admin(request.auth)
    run = start_run(request.auth, [s.model_dump() for s in payload.schools])
    return 201, _run_dict(_run_or_404(run.pk))


@admin_progression_router.post(
    "/runs/{run_id}/schools/{school_id}/execute/",
    response={200: SchoolProgressionOut, **_RUN_ERR},
)
def post_execute(request, run_id: int, school_id: int):
    """Progress one school (one transaction). The wizard calls this per school."""
    _require_admin(request.auth)
    run = _run_or_404(run_id)
    _school_progression(run_id, school_id)
    return 200, execute_school(run, school_id, request.auth)


@admin_progression_router.get("/runs/", response={200: List[RunOut], 403: ErrorResponseSchema})
def list_runs(request):
    _require_admin(request.auth)
    runs = ProgressionRun.objects.select_related("started_by").order_by("-run_id")[:50]
    return 200, [_run_dict(r) for r in runs]


@admin_progression_router.get("/runs/{run_id}/", response={200: RunDetailOut, **_RUN_ERR})
def get_run(request, run_id: int):
    _require_admin(request.auth)
    run = _run_or_404(run_id)
    return 200, {**_run_dict(run), "schools": _school_rows(run)}


@admin_progression_router.get(
    "/runs/{run_id}/schools/{school_id}/",
    response={200: RunSchoolDetailOut, **_RUN_ERR},
)
def get_run_school(request, run_id: int, school_id: int):
    _require_admin(request.auth)
    sp = (
        SchoolProgression.objects.select_related(*_SP_YEARS)
        .filter(run_id=run_id, school_id=school_id)
        .first()
    )
    if sp is None:
        raise NotFound(f"School {school_id} is not part of run {run_id}.")
    name = (
        Partner.objects.filter(partner_id=school_id).values_list("partner_name", flat=True).first()
    )
    return 200, {**_school_dict(sp, name), "row_log": row_log_summary(sp)}


# ── F-M10-8: undo ─────────────────────────────────────────────────────────────


@admin_progression_router.post(
    "/runs/{run_id}/schools/{school_id}/undo/",
    response={200: SchoolProgressionOut, **_RUN_ERR},
)
def post_undo(request, run_id: int, school_id: int):
    """Put a completed school back on its old year (only before new-year writes)."""
    _require_admin(request.auth)
    return 200, undo_school(_school_progression(run_id, school_id), request.auth)


# ── F-M10-5: release ───────────────────────────────────────────────────────────


@admin_progression_router.post(
    "/runs/{run_id}/schools/{school_id}/release/",
    response={
        200: SchoolProgressionOut,
        403: ErrorResponseSchema,
        404: ErrorResponseSchema,
        409: ErrorResponseSchema,
    },
)
def release(request, run_id: int, school_id: int):
    """Unfreeze a failed school on its old year without retrying."""
    _require_admin(request.auth)
    return 200, release_school(_school_progression(run_id, school_id), request.auth)
