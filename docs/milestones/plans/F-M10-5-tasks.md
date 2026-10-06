# F-M10-5 Execution Progress

Plan: `docs/milestones/plans/F-M10-5-plan.md`. Not committing; the human commits manually.
**Status:** Complete 2026-09-29. Migration 0037 is not applied to dev yet.

## Milestone 1: Models + freeze service
- [x] `models/progression.py`:
  - `ProgressionRun`, `SchoolProgression` (status, graduate ids, counts, warnings, error, undo fields; `uniq_unfinished_progression_per_school`), `ProgressionRowLog` (with `meta` for F-M10-8)
  - `FROZEN_STATUSES = (queued, running, failed)`
  - migration `0037_progression_models`
- [x] `services/progression/freeze.py`: `frozen_school_ids`, `is_school_frozen`, `recompute_run_status`, `release_school`

## Milestone 2: Scope, middleware, permissions, school list
- [x] `rbac/scope.py`:
  - `schools_visible_to` excludes frozen schools for non-admins, and `get_school_or_403` gives non-admins 404 for them
  - new `frozen_schools_in_scope_count`
- [x] `middleware/progression_freeze.py`: any non-GET/HEAD/OPTIONS request to `/api/schools/{id}/…` for a frozen school returns 409 `school_progressing`, for every role. Registered in `MIDDLEWARE`
- [x] `GET /auth/me/permissions/` returns `can_modify=False` while frozen
- [x] `GET /api/schools/` returns `progressing_count`
- [x] `routes.py` conflict handler passes a custom `ConflictError.error_code` through (the default stays `"conflict"`; no existing code used a custom one)

## Milestone 3: Release + banner
- [x] `api/admin_progression_api.py` (admin only): `POST /api/admin/progression/runs/{run_id}/schools/{school_id}/release/`, 409 `release_not_allowed` unless the school is failed
- [x] SchoolListPage: a dismissible info banner "N of your schools are being moved to the next academic year…"
- [x] Tests:
  - backend `tests/progression/test_f_m10_5_freeze.py` (22):
    - the constraint; frozen statuses
    - visibility for CO and admin; list count; permissions
    - **every real `/api/schools/{id}/…` route blocked for POST, PATCH and DELETE**, collected from the router
    - reads allowed; unfrozen and completed schools writable; non-school routes unaffected
    - release service and endpoint
  - frontend SchoolListPage banner (2)
- [x] **Backend:** 1013 passed; 23 errors were **network failures to the RDS test DB** ("could not translate host name", "server closed the connection unexpectedly" during a 24-minute run). The 3 affected files re-run 60/60 green.
- [x] **Frontend:** 252 passed. Typecheck and lint on touched files clean.

## Deviations
- **Conflict handler:** `routes.py` now emits a specific `error_code` when one is given. That's needed for `release_not_allowed` and, later, `undo_not_allowed`.
- **`progressingCount` is optional** in the TS response type (defaults to 0), so existing mocks and older responses type-check.

## Blockers
- None
