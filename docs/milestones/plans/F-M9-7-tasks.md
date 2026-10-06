# F-M9-7 Execution Progress

Plan: `docs/milestones/plans/F-M9-7-plan.md`. Not committing; the human commits manually.
**Status:** Complete 2026-09-27, apart from the manual check (the human does this).

Inherits F-M9-3 Open Question 1: assignments from any academic year are counted, the same as the tab. This was a default, not a confirmed decision.

## Milestone 1: Rows + endpoint
- [x] `services/exports/volunteers.py`: `ALL_VOLUNTEERS_HEADER` (with `school_city`), `all_volunteer_rows(partner_ids)` built on `volunteer_rows_for_schools`
- [x] `GET /api/exports/volunteers.csv?search=` (`export_all_volunteers`)
- [x] Tests (15):
  - rows grouped by school, then volunteer
  - shared worknode: the volunteer appears under both schools, and each row lists only that school's assignments
  - each school's rows equal `school_volunteer_rows`; the given order is kept; a school with no worknode adds no rows; empty input
  - query count doesn't grow with the number of schools; no duplicate column names
  - API: admin sees every school, with an audit row; search matches the CO name and is logged; CHO and CO scope; header only when there are no schools; no active year 404; 401
- [x] Full backend suite: 924 passed

## Milestone 2: Frontend
- [x] `exportAllVolunteers(search)` in `exports.service.ts`
- [x] `SchoolListPage.tsx`: "All volunteers" menu item
- [x] Vitest: menu test + service params test
- [x] Full frontend suite: 238 passed (clean first run)
- [x] Lint on touched files: no errors
- [x] Manual check (verified by the user 2026-09-28): as an admin, export all volunteers; compare a few schools against their Volunteers tabs

## Deviations
- **Column rename.** The school city column is `school_city`, the same as F-M9-6. The planned header would have had two `city` columns.

## Blockers
- None
