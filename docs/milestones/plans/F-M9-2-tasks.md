# F-M9-2 Execution Progress

Plan: `docs/milestones/plans/F-M9-2-plan.md`. Not committing; the human commits manually.
**Status:** Complete 2026-09-27, apart from the manual Excel check, which the human does in a browser.

## Milestone 1: Backend service + tests
- [x] `services/exports/children.py`: `CHILDREN_HEADER`, `school_children_rows` (wraps `list_children`, adds removal-log subqueries, orders class → bucket → name)
- [x] Service tests in `tests/exports/test_f_m9_2_children_export.py`: 17 passed

## Milestone 2: Endpoint + API tests
- [x] `GET /api/schools/{school_id}/exports/children.csv` (`api/exports_api.py::export_school_children`)
- [x] API tests (9): CSV body/headers, tab filters, audit row with non-empty filters, CO 403 / own school 200, unknown school 404, no active year 404, bad status 422, no token 401
- [x] Full backend suite: 832 passed

## Milestone 3: Frontend
- [x] `exports.service.ts`:
  - `exportParams` sends `true` as `"true"`, drops `false` and `""`, and no longer trims strings
  - `ChildrenExportFilters`, `exportSchoolChildren`
- [x] `ChildrenTab.tsx`: `ExportButton` in the header, before Enroll Child; shown regardless of `canModify`; disabled while loading or on load error
- [x] Vitest:
  - `download.test.ts`: `exportParams` + `exportSchoolChildren` URL and params
  - `ChildrenTab.test.tsx`: 3 export tests
- [x] Full frontend suite: 223 passed (26 files)
- [x] Lint/typecheck: touched files clean (ChildrenTab.tsx has no new problems)
- [x] Manual check (verified by the user 2026-09-28): Excel, row count equals "N results", Hindi names, `export_log` row. **The human does this.**

## Deviations
- **Service function name.** It's a named export `exportSchoolChildren`, not `exportsService.schoolChildren`, to match the other service files (`fetchChildren`, etc.). The empty `exportsService` object was removed.
- **`exportParams` no longer trims strings.** The tab sends `debouncedSearch` untrimmed, so trimming would make the file differ from the screen when there's a trailing space. Strings are now sent as-is and only `""` is dropped. I updated the F-M9-1 test to match.
- **An existing test changed.** `ChildrenTab.test.tsx::test_search_input_updates_and_clear_button_resets_it` picked the clear button by global index (`getAllByRole("button")[1]`), which the new header button shifted. It now finds the button inside the search field. The component itself is unchanged.
- **One flaky run.** The first full frontend run had one failure while the backend suite was running at the same time (the CPU-contention timeouts noted in `vitest.config.ts`). The re-run on an idle machine passed 223/223.

## Blockers
- None
