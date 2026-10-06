# F-M10-3 Execution Progress

Plan: `docs/milestones/plans/F-M10-3-plan.md` (Resolved Decisions 2026-09-29). Not committing; the human commits manually.
**Status:** Complete 2026-09-29. No migrations.

## Milestone 1: Helper + slot-side reads
- [x] `current_year_q(prefix)` in `services/academic_year/queries.py` replaces `active_year_slot_q`. It filters on the school's active school-year, with no extra query and no dependence on the global flag
- [x] `get_active_session` uses the school's school-year (feeds the Calendar tab and the holiday window)
- [x] `get_session_defaults` labels the dialog with the school's own year
- [x] Switched: `list_slots`, R7 overlap (`create_slot`, `edit_slot`), R6, schedule, volunteers list

## Milestone 2: Classes, buckets, names
- [x] `list_classes_for_school`: `current_year_q()`
- [x] `list_buckets_for_school` and `list_sections_for_class`: current year **or a null school-year** (legacy fallback, 0 in dev)
- [x] Bucket name pre-checks (`create_bucket` / `edit_bucket`) match the DB slug constraint (active rows only), so an archived "Group A" never blocks a new one

## Milestone 3: Counts + exports
- [x] `get_school_stats` classes count; schools-summary bucket count (same scope as the Buckets tab)
- [x] Schools summary and gap report: term dates and the year label come from each school's own school-year. `schools_summary_rows(partner_ids)` and `gap_rows(partner_ids)` no longer take `active_year`, and callers and tests are updated
- [x] Tests:
  - new `tests/academic_year/test_f_m10_3_year_scope.py` (15)
  - M9 year-filter tests rewritten to school-year semantics (older-year school sees its own data; global flag doesn't scope; no active school-year sees nothing)
  - F-M9-5 term-date test split into "archived school-year ignored" and "school on an older year shows its own dates"
  - M9 query caps back to 3 and 4
- [x] Full backend suite: **1006 passed**. `makemigrations --check` clean; lint on touched files clean
- [x] Grep check: global-year reads remain only for the label, the export 404 guards, the session-defaults fallback, and school-year creation

## Deviations
- **Row lookups not changed.** Bucket lookups in enroll, edit and bucket_children, and the soft-delete guards, look up rows by id or by a specific class. Progression archives old-year rows (`is_active=False`), so those reads were already scoped correctly and only list reads needed the filter.
- **Legacy fallback for sections.** Sections with no school-year stay visible (as holidays will in F-M10-4) rather than silently disappearing. The Day-1 prod profile should confirm the count.
- **Export signatures.** They lost their `active_year` parameter, because the year now comes from each school.

## Blockers
- None
