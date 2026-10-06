# F-M9-6 Execution Progress

Plan: `docs/milestones/plans/F-M9-6-plan.md`. Not committing; the human commits manually.
**Status:** Complete 2026-09-27, apart from the manual check (the human does this).

## Milestone 1: No-behaviour-change refactor of `list_children`
- [x] `services/children/queries.py`: `filter_child_status(qs, status)` and `annotate_current_placement(qs)` extracted; `list_children` uses both, with the same signature, filters and ordering
- [x] Children and bucket suites: 173 passed, unchanged; F-M9-2 tests: 26 passed

## Milestone 2: Rows + endpoint
- [x] `services/exports/children.py`:
  - extracted `_child_row` / `_with_removal` / `_ORDER`, shared by both exports
  - `ALL_CHILDREN_HEADER`, `all_children_rows(partner_ids, status)`
- [x] `GET /api/exports/children.csv?search=&status=` (`export_all_children`)
- [x] Tests (18):
  - rows grouped by school, in name order; each school's rows equal `school_children_rows` for all / active / inactive
  - status filters; removed children excluded; only the given schools; empty input
  - query count doesn't grow with the number of schools; header has no duplicate column names
  - API: admin sees every school, with an audit row; search and status narrow the rows and are logged; CO and CHO scope; header only when there are no schools; bad status 422; no active year 404; 401
- [x] Full backend suite: 909 passed

## Milestone 3: Frontend
- [x] `exportAllChildren(search)` in `exports.service.ts` (sends `status=all`)
- [x] `SchoolListPage.tsx`: "All children" added to the Export options. With 2 options the button now opens a menu.
- [x] Vitest:
  - the existing summary export test now picks from the menu
  - new "All children" menu test
  - service params test
- [x] Full frontend suite: 236 passed (clean first run)
- [x] Lint/typecheck on touched files: clean (only the existing `userName` warning in `SchoolListPage.tsx`)
- [x] Manual check (verified by the user 2026-09-28): as an admin, export all children; active rows equal the sum of `active_children` in the schools summary; open in Excel

## Deviations
- **Column rename.** The school city column is `school_city`, not `city`. The children roster already has its own `city` column, so the planned header would have had two `city` columns. A test now checks the header has no duplicates. M9.md and the F-M9-6/7/8 plans are updated; the gap report uses `school_city` too, for consistency.
- **Helper name.** The status helper is public (`filter_child_status`, not `_filter_status`) because the exports module imports it.

## Blockers
- None
