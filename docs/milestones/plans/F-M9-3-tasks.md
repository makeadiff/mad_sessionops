# F-M9-3 Execution Progress

Plan: `docs/milestones/plans/F-M9-3-plan.md`. Not committing; the human commits manually.
**Status:** Complete 2026-09-27, apart from the manual check (the human does this).

Open Question 1 was not answered when the build started. Default used: the plan's recommendation, matching the tab (active assignments at the school, any academic year). Limiting to the active year would be a single extra filter in `volunteer_rows_for_schools`, and it would also apply to F-M9-7.

## Milestone 1: Service + tests
- [x] `services/exports/volunteers.py`: `VOLUNTEERS_HEADER`, `format_assignment`, `volunteer_rows_for_schools` (3 queries for any number of schools), `school_volunteer_rows`
- [x] Service tests (14):
  - assignment text; bucket without a class; ordering; subject normalisation
  - inactive user, other worknode, and soft-deleted assignment / slot-class / slot all excluded
  - an assignment at another school isn't listed here
  - counts equal the Volunteers tab (`list_school_volunteers`)
  - no worknode gives no rows
  - query count ≤ 3

## Milestone 2: Endpoint + API tests
- [x] `GET /api/schools/{school_id}/exports/volunteers.csv` (`export_school_volunteers`)
- [x] API tests (5): CSV + filename + audit row + phone escaped as text, 403, 404, no-active-year 404, 401
- [x] Full backend suite: 851 passed

## Milestone 3: Frontend
- [x] `exportSchoolVolunteers` in `exports.service.ts`
- [x] `VolunteerListTab.tsx`: `ExportButton` at the right end of the header row, in the populated state only
- [x] Vitest: service URL test; tab tests (button calls the export; hidden in the `no_worknode` and `no_volunteers` states)
- [x] Full frontend suite: 227 passed. The first run had 5 CalendarTab timeouts while the machine was under load; the file passes 8/8 on its own and the re-run passed everything. There were no calendar changes.
- [x] Lint/typecheck on touched files: clean
- [x] Manual check (verified by the user 2026-09-28): export a real school; row count equals the tab's badge; open in Excel

## Deviations
- **Test fixture only:** buckets in the test data use `section_code=None`, because the column is a nullable single character.
- **Phone numbers starting with `+`** are exported as `'+91…`. This is the formula-injection guard from F-M9-1, and Excel shows the value as text. It's covered by a test.

## Blockers
- None
