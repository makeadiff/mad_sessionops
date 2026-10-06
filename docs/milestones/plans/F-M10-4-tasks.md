# F-M10-4 Execution Progress

Plan: `docs/milestones/plans/F-M10-4-plan.md`. Not committing; the human commits manually.
**Status:** Complete 2026-09-29. Migrations 0035/0036 are not applied to dev yet.

## Milestone 1: Migration + backfill
- [x] `SchoolHoliday.school_academic_year_id` FK (null, PROTECT, `db_column="school_academic_year_id"`)
- [x] `0035_holiday_school_year` (schema) and `0036_backfill_holiday_school_year`:
  - links each holiday to its school's active school-year and leaves schools with none null
  - prints the linked and unlinked counts
  - DB-alias safe; the reverse is a no-op
- [x] Backfill test

## Milestone 2: Services
- [x] `services/holidays/queries.py::current_year_holidays_q()`: the school's own year **or** a null school-year (legacy fallback)
- [x] `create_holiday`:
  - stores the school's active school-year
  - the R-cal-3 overlap check is scoped to the current year and legacy rows
  - date edits go through create, so they keep the link
- [x] `list_holidays` is scoped the same way. Old holidays are **not archived**; they drop out of view after progression
- [x] Tests (7):
  - a new holiday is linked; a date edit keeps the link
  - after an archived-year swap, old holidays are hidden but not archived, and the same dates don't conflict
  - overlap within the year is still rejected
  - legacy null holidays are visible and checked
  - the backfill links holidays and leaves school-less ones null
- [x] Holiday suites 35/35; full backend suite **1013 passed**; `makemigrations --check` clean; lint clean

## Deviations
- None

## Blockers
- None
