# F-M9-4 Execution Progress

Plan: `docs/milestones/plans/F-M9-4-plan.md`. Not committing; the human commits manually.
**Status:** Complete 2026-09-27, apart from the manual check (the human does this).

## Milestone 1: Service + tests
- [x] `services/exports/timetable.py`: `TIMETABLE_HEADER`, `school_timetable_rows` (4 queries for any number of slots)
- [x] Shared test factories: `tests/exports/factories.py`, used from F-M9-4 onward
- [x] Service tests (11):
  - ordering by day, time and class; volunteer names joined and sorted, with count
  - a soft-deleted assignment isn't counted; children counted from active placements only
  - an empty slot gets a blank row; a bucket without a class gets a blank class; subject name normalised
  - inactive slot and slot-class excluded
  - parity with `get_school_schedule`; no slots gives no rows; query count ≤ 4

## Milestone 2: Endpoint + API tests
- [x] `GET /api/schools/{school_id}/exports/timetable.csv` (`export_school_timetable`)
- [x] API tests (5): CSV + filename + audit row, 403, 404, no-active-year 404, 401
- [x] Full backend suite: 867 passed

## Milestone 3: Frontend
- [x] `exportSchoolTimetable` in `exports.service.ts`
- [x] `SlotListTab.tsx`: `ExportButton` before the agenda/grid toggle, disabled when there are no slots, not role-gated
- [x] Vitest:
  - new `__tests__/schools/slots/SlotListTab.test.tsx` (click calls the export; disabled with no slots)
  - service URL test
- [x] Full frontend suite: 230 tests.
  - The first run had 2 CalendarTab failures; a second run passed everything.
  - CalendarTab passes 8/8 on its own, and the calendar code hasn't changed.
  - The failing tests took 1.1–1.5s, just over the default 1s `waitFor` timeout. This is an existing timing flake under full-suite load, not caused by this feature.
- [x] Lint/typecheck on touched files: clean
- [x] Manual check (verified by the user 2026-09-28): export a real school's timetable; the day and time order matches the Slots tab; print preview in Excel

## Deviations
- **Test helpers:** added `tests/exports/factories.py` (shared ORM factories plus auth and CSV helpers) instead of copying fixtures again. The F-M9-3 tests keep their own helpers, unchanged.
- **Empty slot rows** leave `children_in_bucket` blank, since there's no bucket. The plan listed only class, bucket and subject as blank.

## Blockers
- None

## Flagged (not fixed, out of scope)
- `__tests__/schools/calendar/CalendarTab.test.tsx` is flaky under full-suite load (default 1s `waitFor`). Worth a separate fix, e.g. a `findBy` with a longer timeout.
