# F-M10-8 Execution Progress

Plan: `docs/milestones/plans/F-M10-8-plan.md`. Not committing; the human commits manually.
**Status:** Complete 2026-09-30. No migrations (the `ProgressionRowLog.meta` field was already added in F-M10-5).

## Milestone 1: can_undo
- [x] `services/progression/undo.py::can_undo(sp) -> (bool, reason)`. Undo is allowed only when:
  - the school is `completed`
  - no row on the new school-year exists outside the run's own created rows (checked for classes, sections, slots, school volunteers, batch rows, term dates and holidays)
  - no child placement points at the new classes or sections outside the log
  - no child was enrolled after the run finished
  - no logged row, created or archived, has been edited since

  When undo isn't allowed, it returns the first reason in plain words, e.g. "A slot was added in 2026-2027 after progression."

## Milestone 2: undo_school + endpoint
- [x] `undo_school(sp, user)`: one transaction that locks the school progression and the new school-year and re-checks `can_undo` (otherwise 409 `undo_not_allowed`). Then:
  - **created rows are soft-deleted first** (`removed=True`), so the one-active-school-year and section-slug rules never clash
  - archived rows are restored (`is_active=True`); graduates' retired links also get `removed=False`
  - graduated children are reactivated, and their `graduated` removal log is retired
  - status becomes `undone`, and the run status is recomputed
  - **the global year is never flipped back**
- [x] `POST /api/admin/progression/runs/{run}/schools/{school}/undo/` (admin only). Run-detail school rows gain `can_undo` and `undo_block_reason`
- [x] Tests `tests/progression/test_f_m10_8_undo.py` (16):
  - **snapshot**: every pre-existing row across 14 tables is back exactly as it was, and every row the run created is soft-deleted; the school is back on its old school-year
  - graduates are active again
  - the global year is kept
  - an undone school can be progressed again, ending in the same state
  - undo allowed straight after completion
  - **blocked by each kind of new-year write**: a slot, a bucket, term dates, a holiday, a new enrolment, or an edit to a created row
  - undo requires `completed` (undone, failed and queued give 409)
  - API: `can_undo` flag and reason; undo 200; a second undo is 409 `undo_not_allowed`; CO 403
- [x] Progression suites 86/86
- [x] **Full backend suite: 1098 passed, 1 error**, a dropped RDS connection in `test_m9_active_year_filter.py` during a 41-minute run. That file re-runs 13/13. `makemigrations --check` clean; lint clean

## Deviations
- **Test fixture:** the `ctx` fixture is defined locally in the undo tests. Importing it from the F-M10-7 test module tripped ruff F811.
- **Syncs block undo:** undo refuses after *any* new-year write, including a realtime-sync `SchoolVolunteer` row. That's the safe reading of "until the first new-year write".

## Blockers
- None
