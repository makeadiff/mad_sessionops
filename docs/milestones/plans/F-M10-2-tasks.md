# F-M10-2 Execution Progress

Plan: `docs/milestones/plans/F-M10-2-plan.md`. Not committing; the human commits manually.
**Status:** Complete 2026-09-29. Migration 0034 is not applied to dev yet.

## Milestone 1: Constraint
- [x] `SchoolAcademicYear` constraint `uniq_active_say_per_school` (`school_id` where `is_active` and not `removed`)
- [x] Migration `0034_one_active_school_year`: a `RunPython` precheck that aborts and lists the offending schools (it never auto-fixes), then `AddConstraint`. DB-alias safe; reversible (the precheck's reverse is a no-op)
- [x] Tests (4): second active school-year rejected by the DB; archived or removed extras allowed; precheck passes on clean data and names duplicates

## Milestone 2: Services
- [x] `get_school_academic_year(school_id)`
- [x] `get_or_create_school_academic_year` uses it, and creates inside a savepoint (a concurrent first write that hits the constraint re-reads the winner)
- [x] `enroll` and `reactivate` resolve the school-year via the helper (no more `.get()` crash or 409). The class must belong to the school's current school-year (400 otherwise)
- [x] Tests (7):
  - the helper returns an existing non-global-year row, or creates one for the global year
  - enroll into a current-year class works; into an archived-year class, 400
  - reactivation into the prior closed class across a year boundary works
  - reactivation into a different closed class, 400
  - reactivation into an archived-year class, 400
- [x] Full backend suite, 2026-09-29: 976 passed, 13 failed, all in **two fixture files** that deliberately built a *second active* school-year:
  - `test_m9_active_year_filter.py`
  - `test_f_m9_8_gap_report.py::test_term_dates_for_other_year_still_a_gap`

  They now create the old year's school-year as **archived** (`is_active=False`), which is the real state after progression. Both files pass 34/34. No other test was affected, so the suite is green.
- [x] `makemigrations --check` clean; migration DB-alias check passed; lint on touched files clean

## Deviations
- **Behaviour change (intended):** enrolling or reactivating in a school with no school-year now creates one for the global year, instead of 409 "No active academic year binding". No test asserted the old 409.
- **Fixture corrections:** two M9 test fixtures now use an archived old-year school-year (see above). F-M10-3 rewrites the M9 year-filter tests anyway.

## Blockers
- None
