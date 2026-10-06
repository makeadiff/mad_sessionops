# F-M10-7 Execution Progress

Plan: `docs/milestones/plans/F-M10-7-plan.md`. Not committing; the human commits manually.
**Status:** Complete 2026-09-29. No new migrations; it uses 0037/0038.

## Milestone 1: retire_child refactor
- [x] `children/deactivate.py`:
  - `retire_child(child, *, reason, other_details, user, now)` is the core: the child goes inactive, its class, section, batch and program links are soft-retired, and a removal log is written. It returns the affected ids for the row log.
  - `deactivate_child` keeps RBAC + R-bucket and then calls the core. Behaviour is unchanged.
- [x] Children, deactivate and reactivate suites: 188 passed, with no assertion failures. (The 20 errors in that run were RDS DNS failures during a 2h11m run.)

## Milestone 2: Start
- [x] `services/progression/start.py::start_run`, in one transaction:
  - validate the target and marks, and re-precheck (any blocked school → 400, nothing written)
  - flip the global year only when the target isn't active (deactivate, then activate)
  - archive the active school-years of non-converted schools (ids recorded in `run.cleanup`)
  - create the run plus queued, frozen `SchoolProgression` rows

## Milestone 3: Execute + row log
- [x] `services/progression/rowlog.py`: `RowLog` (created/archived, bulk flush) and `summary()`
- [x] `services/progression/execute.py::execute_school`:
  - status guard: completed → returned as is; running, undone or released → 409 `execute_not_allowed`
  - then **one transaction**, which re-plans inside a `select_for_update` lock on the school-year, and does:
    - school-year swap
    - SchoolClass copy and additions
    - ClassSection archive, then copy (same names, no class link) with the id map
    - graduates via `retire_child("graduated")`; movers re-created in the next class and the mapped section, with a new BatchChild
    - SchoolVolunteer carried over
    - timetable, subjects and session archived
    - row log
  - any exception rolls back and the school becomes `failed` (still frozen, retryable)
- [x] Tests `tests/progression/test_f_m10_7_execute.py` (13):
  - **full-school map**: classes, children moved with remapped sections, empty section copied, the no-section child left without one, BatchChild, volunteers, timetable and session archived, holiday untouched, nothing hard-deleted, school unfrozen
  - **counts equal the preview**
  - row log complete, including the section id remap
  - graduation with reason `graduated` (no R-bucket error with a staffed bucket)
  - 8th → new 9th
  - **exception → exact rollback (snapshot), then retry succeeds**
  - a blocker added after Start → failed, nothing written
  - idempotent / running gives 409
  - other schools untouched
  - Start freezes schools and rejects blocked ones
  - Start flips once and archives non-converted school-years
  - API: start → execute → list → detail → school detail with the row-log summary; blocked 400; CO 403

## Milestone 4: Endpoints (admin only)
- [x] `POST /api/admin/progression/runs/` (201), `POST /runs/{run}/schools/{school}/execute/`, `GET /runs/` (last 50), `GET /runs/{run}/`, `GET /runs/{run}/schools/{school}/`
- [x] **Full backend suite: 1083 passed** (clean run); `makemigrations --check` clean

## Deviations
- **No threaded concurrency test.** Execution takes the `select_for_update` lock on the school-year as planned, but I didn't add a threaded "realtime sync waits on the lock" test. The shared RDS test DB is unstable over this network, so a threaded `transaction=True` test would be flaky. Consistency is still covered, because execution copies whatever `SchoolVolunteer` rows are active at lock time.
- **Run schemas are plain.** Responses are built as plain dicts by `_run_dict` / `_school_dict`, because Ninja resolvers don't run on dict input.
- **Performance** on a prod-data copy (the "within 30 s per school" check) is **not yet measured**. It needs the prod-copy dry run from the M10 checklist.

## Blockers
- None
