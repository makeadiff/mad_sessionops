# F-M9-5 Execution Progress

Plan: `docs/milestones/plans/F-M9-5-plan.md` (see its "Revision" section). Not committing; the human commits manually.
**Status:** Complete 2026-09-27, apart from the manual check (the human does this).

## Milestone 1: Export search + bulk CHO lookup
- [x] `services/exports/scope.py::filter_schools_like_page` (name, city or CO name, using the page's trim rule); `export_school_ids` uses it
- [x] `services/schools/queries.py::get_chos_for_schools` (2 queries); `get_chos_for_school` now wraps it
- [x] Tests (10):
  - search: page parity, state not matched, blank means no filter, untrimmed text as typed
  - the API search keeps its M1 state match; `export_school_ids` uses the page search
  - bulk CHO lookup: per school, multi-role string, shared worknode, wrapper parity, query count, empty input
- [x] M1 school list and detail suites unchanged and green, including TC-M1-4-06

## Milestone 2: Summary rows + endpoint
- [x] `services/exports/schools.py`: `SCHOOLS_HEADER`, `schools_summary_rows(partner_ids, active_year)`
- [x] `GET /api/exports/schools.csv?search=` (`export_schools_summary`)
- [x] Tests (14):
  - summary rows: values for every column; page counts equal `get_school_stats`; empty school; term dates from another year ignored; given order kept; empty input; query count doesn't grow with the number of schools; row width
  - API: admin sees all schools ordered by name, with an audit row (`school_id=None`, `school_count`); search matches the page and is logged; CO sees only own schools; user with no schools gets a header only with `school_count=0`; no active year 404; 401
- [x] Full backend suite: 891 passed

## Milestone 3: Frontend
- [x] `exportSchoolsSummary(search)` in `exports.service.ts`
- [x] `SchoolToolbar.tsx`: optional `exportOptions` prop; renders `ExportButton label="Export"` after Sort when given
- [x] `SchoolListPage.tsx`: passes `[{ "Schools summary" }]` with `debouncedSearch`
- [x] Vitest:
  - new `__tests__/schools/SchoolToolbar.test.tsx` (hidden without options, shown with them)
  - `SchoolListPage` test (the export gets the debounced search)
  - service params test
- [x] Full frontend suite: 234 passed.
  - The first run had 1 timing failure (`test_schools_page_clear_search_resets_filter`, 4.2s).
  - That test doesn't select by button position. The file passed 16/16 twice on its own, and the re-run passed everything.
- [x] Lint/typecheck on touched files: clean. `SchoolListPage.tsx:132` has an unused `userName` warning that was already there.
- [x] Manual check (verified by the user 2026-09-28): as an admin and as a CO, search "pune", export; the row count equals the visible schools and the counts match the cards

## Deviations
- **Separate export search.** The export search is a separate helper instead of a change to `filter_schools_by_search`, so M1 TC-M1-4-06 stays intact. This was the user's decision, and it's recorded in the plan's Revision section and in M9.md decision 9.
- **`schools_summary_rows` takes the active year as an argument,** because the view already loads it. This saves a query and makes the term-date filter explicit.
- **Query-count test** measures a 2-school baseline, then checks that 8 schools don't exceed it, instead of asserting a fixed number.

## Blockers
- None
