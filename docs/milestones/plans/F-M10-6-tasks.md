# F-M10-6 Execution Progress

Plan: `docs/milestones/plans/F-M10-6-plan.md`. Not committing; the human commits manually.
**Status:** Complete 2026-09-29. Migration 0038 is not applied to dev yet.

## Milestone 1: Reason + planner + eligibility + target year
- [x] `REMOVED_REASONS` += `("graduated", "Graduated")` (migration `0038_removal_reason_graduated`, choices only). `DeactivateIn` is unchanged, so the CO dialog can't use it
- [x] `services/progression/target.py`: `resolve_target_year()` (the global year while any converted school is behind; otherwise the single later inactive year; "create it" or "ambiguous" reasons) and `validate_target_year()`
- [x] `services/progression/planner.py`: `build_plans(school_ids, target_year, marks, frozen_ids)` → `SchoolPlan`
  - **fixed query count whatever the number of schools or children**, enforced by a test
  - the 8 blocker codes and 6 warning codes
  - class copies, plus classes added for promoted children
  - every section copied, including empty and legacy ones
  - child moves via the catalog `next_class`
  - graduation by class or by child, never double-counted
  - volunteers carried over
  - archive id lists per table
  - preview counts
- [x] `validate_marks()`: unknown graduate child or class ids give 400
- [x] `services/progression/eligibility.py`: every converted school with its eligibility and reason

## Milestone 2: Endpoints (admin only)
- [x] `GET /api/admin/progression/target-year/`. This is used by the F-M10-9 wizard and was brought forward from that plan
- [x] `GET /eligible-schools/?target_year_id=`, `POST /precheck/`, `POST /preview/` (at most 100 schools, 422 otherwise), `GET /preview/{school_id}/children/` (paginated; id, name, class and section only)
- [x] Tests `tests/progression/test_f_m10_6_precheck_preview.py` (35):
  - target-year rules
  - mapping: each class moves up, 8th stays; a class added for promotion; 9th added with 8→9; empty sections copied; graduation counted once, and graduates' links not archived; archive lists
  - every blocker; the warnings (including a legacy section still being copied)
  - read-only; constant query count
  - API: target, eligibility, precheck and preview, unknown graduate 400, wrong target 400, over 100 ids 422, child picker without personal data, non-admins (CO, CHO, CXO) 403
- [x] **Full backend suite: 1070 passed.** `makemigrations --check` clean; migration DB-alias check passed

## Milestone 3: Frontend service
- [x] `lib/api/services/progression.service.ts`: `fetchTargetYear`, `fetchEligibleSchools`, `precheckSchools` and `previewSchools` (automatically split into requests of 100), `fetchPreviewChildren`
- [x] `__tests__/api/progression.service.test.ts` (4)
- [x] **Full frontend suite: 256 passed.** Lint on new files clean

## Deviations
- **Bug caught by the query-count test and fixed:** the planner read `Class.next_class_id` through the lazy FK, which cost one query per class. It now resolves the next class through the already-loaded catalog.
- **`GET target-year/` built here** instead of in F-M10-9, because eligibility and validation needed the same logic.
- **Graduates' links are left out of the archive lists.** F-M10-7 retires them the same way deactivation does, so they're never processed twice.
- **Tooling notes, not product changes:**
  - RDS DNS blips again caused test-run errors; the re-runs were green.
  - A PowerShell edit mis-encoded one test file ("—" became "â€”"). It was repaired.
  - `just` has to be run from Bash, because PowerShell has no `sh`.

## Blockers
- None
