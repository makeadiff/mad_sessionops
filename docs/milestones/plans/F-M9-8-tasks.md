# F-M9-8 Execution Progress

Plan: `docs/milestones/plans/F-M9-8-plan.md`. Not committing; the human commits manually.
**Status:** Complete 2026-09-27, apart from the manual check (the human does this).

Open Question 1 (`SCHOOL_NO_WORKNODE`) wasn't answered. Default: the five spec gap types only. Adding it later is a small change in `gaps.py`: one set difference against the `PartnerWorknode` school ids.

## Milestone 1: Service + tests
- [x] `services/exports/gaps.py`: `GAP_TYPES`, `GAPS_HEADER`, `gap_rows(partner_ids, active_year)`. Each gap is defined the same way its tab shows it and uses the same helpers (`annotate_current_placement`, `volunteer_rows_for_schools`, `format_assignment`).
- [x] Service tests (17):
  - A fully set-up school has no gaps.
  - Each type on its own:
    - term dates missing, including dates set only for another year
    - no slots
    - child with no bucket, including a retired placement; inactive children are ignored
    - slot-class with no volunteer, with entity text and child count; slot-classes on an inactive slot are ignored
    - unassigned volunteer
  - All five types across two schools; defined type order; given school order.
  - Parity with the tabs: the Children tab "Unassigned" filter, and the Volunteers tab count of 0.
  - School columns; empty input; query count doesn't grow with the number of schools.

## Milestone 2: Endpoint + API tests
- [x] `GET /api/exports/gaps.csv?search=` (`export_gap_report`)
- [x] API tests (5):
  - CSV + audit row
  - search narrows the rows and is logged
  - CO scope
  - no active year 404; 401
- [x] Full backend suite: 946 passed. `makemigrations --check` clean; migration DB-alias check passed.

## Milestone 3: Frontend
- [x] `exportGapReport(search)` in `exports.service.ts`
- [x] `SchoolListPage.tsx`: "Gap report" is the last menu item. The menu now reads: Schools summary, All children, All volunteers, Gap report.
- [x] Vitest: menu order test that also runs the gap report; service params test
- [x] Full frontend suite: 240 passed (clean first run)
- [x] Lint/typecheck on touched files: clean
- [x] Manual check (verified by the user 2026-09-28): as a CO, export the gap report; check 2 or 3 gaps against the tabs

## Deviations
- **Plan correction: "one school seeded with each gap gives exactly 5 rows" is impossible.** `SCHOOL_NO_SLOTS` (no active slot) and `SLOT_CLASS_NO_VOLUNTEER` (needs an active slot) can't happen at the same school. The test seeds the five types across two schools instead.
- **Text for slot-class gaps.** The entity text reuses F-M9-3's `format_assignment`, so it includes the class when the bucket has one (e.g. "Monday 10:00-11:00 · 5th · Group A · English"). The detail reads "N children in bucket".
- **Column name.** `school_city`, for consistency with F-M9-6 and F-M9-7.

## Blockers
- None
