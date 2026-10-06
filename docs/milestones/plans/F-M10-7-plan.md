# Feature Plan: F-M10-7 — Start run and execute per school

**Milestone doc:** `docs/milestones/M10.md` → F-M10-7 (the table in Part 1 is the specification)
**Status:** Plan — not started
**Date:** 2026-09-28
**Depends on:** F-M10-1 to F-M10-6

## Overview

**Start**
- Creates the `ProgressionRun`.
- Flips the global year, on the first run only.
- Archives non-converted schools' active school-years.
- Queues and freezes the selected schools.

**Execute**
- Progresses one queued school **in one transaction**, by applying the F-M10-6 plan: create, remap, archive, graduate, and log every row.
- A failure rolls back the school entirely and marks it `failed`. It's still frozen, and it can be retried.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend services | New + Modified | New `services/progression/start.py`, `execute.py`, `rowlog.py`. `children/deactivate.py` is refactored into `retire_child(child, *, reason, other_details, user, now)` (the core, with no RBAC or R-bucket check) plus the existing `deactivate_child` wrapper (RBAC + R-bucket + core). Its behaviour is unchanged |
| Backend API endpoints | New | `POST /api/admin/progression/runs/`; `POST …/runs/{run_id}/schools/{school_id}/execute/`; `GET …/runs/`, `GET …/runs/{run_id}/`, `GET …/runs/{run_id}/schools/{school_id}/` |
| Models / migrations | None | Uses the F-M10-5 models |
| Existing tests | Must stay green | The `deactivate_child` suites (refactor safety net) |
| Documentation | Update | M10 Done log, BUSINESS_RULES R8 enforcement note ("flip performed by progression Start") |

## Low-Level Design

### Start (`start.py::start_run(user, target_year_id, schools[])`), one transaction

1. **Checks:**
   - Resolve and validate the target year (same rules as F-M10-6).
   - Re-run precheck for the selected schools. Any blocked school means 400 with the list.
   - Validate the graduate ids.
2. **Flip,** if the target isn't active: lock both `AcademicYear` rows (`select_for_update`), deactivate the current one and activate the target. The DB's `uniq_active_academic_year` constraint guarantees R8.
3. **Cleanup:** archive (F/F) every active `SchoolAcademicYear` of `Partner.converted=False` schools. Their ids go in `run.cleanup`.
4. **Create** the `ProgressionRun`, plus one `SchoolProgression(status="queued", from_school_academic_year_id=<school's active SAY>, graduate_*…)` per school. This freezes them (F-M10-5).

### Execute (`execute.py::execute_school(run, school_id, user)`)

- **Idempotent:** if the status is `completed`, return it as it is. If it's `running`, return 409 (another tab). If it's `undone` or `released`, return 409.
- Set the status to `running` and `started_at` in their own short transaction.
- Then, inside **one** `transaction.atomic()`:
  1. `select_for_update` the school's active `SchoolAcademicYear`. Syncs that need it wait here.
  2. `plan = build_school_plan(...)`. If there are blockers, raise `ProgressionBlocked(plan.blockers)`.
  3. **School-year:** archive the old one. Create the new one (the target year, `created_by=run.started_by`).
  4. **SchoolClass:** `bulk_create` the copies and additions. Map `class_id → new school_class_id`. Archive the old ones.
  5. **ClassSection:**
     - Archive the old rows **first**, because the slug-uniqueness constraint only covers active rows.
     - `bulk_create` the copies: same name and display name, `school_class_id=NULL`, `section_code=NULL`, new school-year.
     - Map `old section id → new id`.
  6. **Children:**
     - Marked to graduate: `retire_child(child, reason="graduated", …)`.
     - Everyone else:
       - Archive the old `ChildClass`, `ChildClassSection` and `BatchChild` rows.
       - `bulk_create` the new `ChildClass` (the target `SchoolClass`) and the new `ChildClassSection` (the mapped section, if the child had one).
       - Create a `BatchChild` for the new school-year.
  7. **SchoolVolunteer:** `bulk_create` copies for the new school-year and archive the old ones.
  8. **Archive** the old year's `Slot`, `SlotClassSection`, `SlotClassSectionVolunteer`, `ClassSectionSubject` and `ChildSubject` rows (for the old sections), and the `SchoolSessionDetails`.
  9. **Log:** `rowlog.bulk_log(...)` every created row (with `source_row_id`) and every archived row id.
  10. **Finish:** set `to_school_academic_year_id` and `counts`, status `completed`, `finished_at`.
- **Any exception:** the transaction rolls back. Then, in a new transaction, set the status to `failed` with `error` (blocker codes or the exception message; the stack trace goes to Sentry). The school stays frozen.
- **Run status:** recomputed after each school.
  - `completed` when every school is completed, undone or released.
  - `completed_with_failures` when some school is `failed` and none is queued or running.
  - Otherwise it stays `in_progress`.

**How archiving is done:** `queryset.update(is_active=False, updated_by_id=…, updated_at=now)` on ids that are collected first, so they can be logged. `removed` stays False and `deleted_at` stays null (the D027 archived state).

**Performance:** bulk operations, with about 15–20 queries per school whatever its size. The target is a few seconds even for the largest school, well inside the 30 s frontend timeout. It's measured on a prod-data copy (acceptance criterion).

## Business Rules Enforced

- **R8:** an atomic flip at Start.
- **One active school-year per school** (F-M10-2): archive old, create new, in one transaction.
- **R9:** only archive and create; the `graduated` path uses the same soft-retire as deactivate.
- **R10:** a graduated child has a removal log with reason `graduated`.
- **Catalog next class** (F-M10-1): no inference from names.

## Security Review

| Concern | Handling |
|---|---|
| RBAC | ADMIN_ROLES only for Start, Execute and the Run reads |
| Concurrency | The `SchoolAcademicYear` row lock and the status guard (`running` → 409) prevent double execution. Unfinished-progression uniqueness comes from the F-M10-5 constraint |
| Audit | Every row is logged, `created_by` is the admin who started the run, and the run records who started it |

## Testing Strategy

**Backend — `tests/progression/test_f_m10_7_execute.py`** (uses the `tests/exports/factories.py` style)
- **Full fixture school:** 5th–8th, sections (one empty), children in every class (one with no section), volunteers, slots with assignments, a session and a holiday.
  - After execute, assert every table row by row against the M10 Part 1 map.
  - Children are in the next class with remapped section ids (e.g. old 5 → new N).
  - 8th children stay in 8th.
  - The empty section is copied; the child with no section still has none; the holiday is untouched.
- **Contract:** `counts == preview counts`.
- **Graduation:** graduated children are inactive, have a `graduated` log, and are excluded from active counts. No R-bucket error occurs even with a staffed slot-class.
- **9th added, 8→9:** 8th children move to a new 9th `SchoolClass`.
- **Atomicity:** an exception injected at step 7 leaves the school exactly as before (a snapshot of every table), with the status `failed` and the error set. Retrying succeeds.
- **Blocker appears after preview:** status `failed` with the blocker codes, and nothing written.
- **Start:**
  - The flip happens once; a second run doesn't flip.
  - Non-converted schools' school-years are archived and recorded.
  - A blocked school gives 400.
  - The selected schools are frozen.
- **Idempotency:** executing a completed school returns it unchanged; a running one gives 409.
- **Concurrency:** a realtime-sync `_ensure_school_volunteer` running in parallel waits on the lock and lands on the new school-year (using a threaded test with `transaction=True`).
- **Isolation:** a school that isn't progressed is unchanged.
- **`deactivate_child` refactor:** the existing suites stay green.

**Performance (manual):** time execute for the largest school on a prod-data copy.

## Milestones (implementation order)

1. `retire_child` refactor, with the existing deactivate tests green.
2. `start_run` + tests.
3. `execute_school` (steps 1–10) + row log + tests, including atomicity and the contract.
4. Run endpoints + API tests; full backend suite; performance check on a prod copy.

## Open Questions

- None.
