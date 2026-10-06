# Feature Plan: F-M9-8 — Ops gap report

**Milestone doc:** `docs/milestones/M9.md` → F-M9-8 (Should have)
**Status:** Built 2026-09-27; see `F-M9-8-tasks.md`
**Date:** 2026-09-27
**Depends on:**
- F-M9-5 (the Schools toolbar Export menu, and the export-only page search `filter_schools_like_page`)
- F-M9-3 (`volunteer_rows_for_schools`)
- F-M9-6 (`annotate_current_placement`)

## Overview

This adds **Gap report** to the Schools page **Export** menu. It downloads a to-do list of setup that's still missing across the user's schools, with one row per gap.
- **Filtering:** ops can sort and filter the file by school or by gap type.
- **A fully set-up school** produces no rows.
- **Main use:** weekly follow-up on setup.

## Gap definitions

Each gap is defined the same way the relevant tab shows it, so a gap in the file is visible on screen.

| gap_type | Detected when | entity_id / entity_name / detail | Same as the tab |
|---|---|---|---|
| `SCHOOL_NO_TERM_DATES` | No active `SchoolSessionDetails` for the active year (`get_active_session` filter) | — / — / "No term dates set for {year}" | Calendar tab shows no session |
| `SCHOOL_NO_SLOTS` | No active `Slot` for the school | — / — / "No weekly slots" | Slots tab empty state |
| `CHILD_NO_BUCKET` | Active child (`is_active`, not removed) with no active `ChildClassSection` | child_id / full name / class name | Children tab, "Unassigned" filter, Active status |
| `SLOT_CLASS_NO_VOLUNTEER` | Active slot-class on an active slot with 0 active assignments | slot_class_section_id / "Monday 10:00-11:00 · Group A · English" / bucket's child count | Slots tab shows a slot-class with no volunteers |
| `VOLUNTEER_UNASSIGNED` | Volunteer matched to the school (F-M9-3 matching) with `slot_class_count = 0` | user_id / name / contact | Volunteers tab card with no assignment |

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend models | None | Read only |
| Backend services | New | `services/exports/gaps.py`: `GAPS_HEADER`, `GAP_TYPES`, `gap_rows(partner_ids)` |
| Backend API endpoints | New | `GET /api/exports/gaps.csv?search=` on `exports_router` |
| Frontend components | Modified | `SchoolListPage.tsx`: add the "Gap report" export option |
| Frontend API | Modified | `exports.service.ts`: `exportGapReport(search)` |
| Database migrations | No | — |
| Existing tests | None affected | — |
| Documentation | Update | M9.md Done log (and M9 marked feature-complete), tasks file |

## High-Level Design

```
SchoolListPage → Export ▸ Gap report → exportGapReport(debouncedSearch)
  → GET /api/exports/gaps.csv?search=…
      year = get_active_academic_year() → ids = export_school_ids(user, search)
      rows = gap_rows(ids, year) → log_export("gap_report", school_count=len(ids))
      → build_csv_response("gaps_all_…")
```

**Key decisions**
- **One bulk query per gap type** across every school in scope, about 8 queries in total whatever the number of schools.
- **Reuse, don't redefine:**
  - `CHILD_NO_BUCKET` uses `annotate_current_placement` from F-M9-6, filtered on `_current_section_id__isnull=True`, exactly like `list_children(unassigned=True)`.
  - `VOLUNTEER_UNASSIGNED` uses `volunteer_rows_for_schools` from F-M9-3 and filters rows with count 0.
- **Order:** school name (the `export_school_ids` order), then the gap-type order in the table above (school-level gaps first), then entity name.

## Low-Level Design

### Backend

**Service: `sessionops/services/exports/gaps.py`**

```python
GAP_TYPES = ["SCHOOL_NO_TERM_DATES", "SCHOOL_NO_SLOTS", "CHILD_NO_BUCKET",
             "SLOT_CLASS_NO_VOLUNTEER", "VOLUNTEER_UNASSIGNED"]
GAPS_HEADER = ["school_id", "school_name", "school_city", "co_name", "gap_type",
               "entity_id", "entity_name", "detail"]

def gap_rows(partner_ids: list[int], active_year: AcademicYear) -> list[list]:
```

- **Partner map:** `{partner_id: (name, city, co_name)}` from one query.
- **Term dates:** the set of `school_id`s with an active session for `active_year`. Schools not in the set get `SCHOOL_NO_TERM_DATES`.
- **Slots:** the set of `school_id`s with an active slot. Schools not in the set get `SCHOOL_NO_SLOTS`.
- **Children with no bucket:**
  - `annotate_current_placement(Child.objects.filter(school_id__in=ids, is_active=True, removed=False))`, filtered on `_current_section_id__isnull=True`.
  - Selects `child_id`, the names, `school_id` and `current_class_name`.
- **Slot-classes with no volunteer:**
  - `SlotClassSection` (active, on an active slot, at a school in `ids`), annotated with `Count` of assignments filtered active and not removed, then filtered to count 0.
  - Uses `select_related` for the slot, section and subject.
  - Child counts come from one grouped `ChildClassSection` query.
- **Unassigned volunteers:** `volunteer_rows_for_schools(ids)`, keeping rows where `slot_class_count == 0`.

**API**

```python
@exports_router.get("gaps.csv")
def export_gap_report(request, search: Optional[str] = None):
    year = get_active_academic_year()
    ids = export_school_ids(request.auth, search)
    rows = gap_rows(ids, year)
    log_export(request.auth, "gap_report", school_count=len(ids),
               filters=_non_empty({"search": search}), row_count=len(rows))
    return build_csv_response(export_filename("gaps", "all"), GAPS_HEADER, rows)
```

### Frontend

- **`exports.service.ts`:** `exportGapReport(search?)` downloads `/exports/gaps.csv`, with fallback filename `gaps_all.csv`.
- **`SchoolListPage.tsx`:** append `{ label: "Gap report", onExport: () => exportGapReport(debouncedSearch) }`, as the last menu item.

## Business Rules Enforced

- **R13:** scope via `export_school_ids`.
- **R8:** the term-date gap is measured against the single active year; 404 when there isn't one.
- **R9:** only active, non-removed records count as either present or missing.
- **M6 R-bucket / R2:** the report flags slot-classes with no volunteer. It doesn't flag over-staffed ones, which the product already blocks when saving.

## Security Review

| Concern | Handling |
|---|---|
| Auth / RBAC | JWT; no `school_id` input |
| Input | `search` goes to ORM `icontains` |
| Personal data | Child names, and volunteer names and phone numbers (only for unassigned volunteers, so ops can call them); audit row |

## Testing Strategy

**Backend — `tests/exports/test_f_m9_8_gap_report.py`**
- **Each gap type fires on its own:**
  - The five gap types seeded across two schools give one row each, in the defined order. (One school cannot have all five: `SCHOOL_NO_SLOTS` and `SLOT_CLASS_NO_VOLUNTEER` are mutually exclusive. Corrected during the build.)
  - Each gap type is also tested alone, both detected and not detected.
- **Fully set-up school:** term dates, slots, every child in a bucket, every slot-class staffed and every volunteer assigned gives a header-only file.
- **Parity with the tabs:**
  - The `CHILD_NO_BUCKET` rows equal `list_children(school, status="active", unassigned=True)`.
  - The `VOLUNTEER_UNASSIGNED` rows equal the volunteers with `active_slot_class_count == 0` in `list_school_volunteers`.
- **Term dates:** a session for a non-active year still counts as a gap.
- **Excluded records:**
  - An inactive slot doesn't satisfy `SCHOOL_NO_SLOTS`.
  - A soft-deleted assignment still leaves the slot-class flagged as `SLOT_CLASS_NO_VOLUNTEER`.
- **Scope and search:**
  - A CO gets gaps only for their own schools.
  - Search narrows the schools covered.
- **Query count:** constant for 2 schools versus 6.
- **API:** 200 with `gaps_all_{date}.csv`; an audit row (`gap_report`, `school_count`); 404 when no year is active; 401 without a token.

**Frontend**
- `exportGapReport` params test.
- The menu shows all four items in order: Schools summary, All children, All volunteers, Gap report.

**Manual:** as a CO, export the gap report and check two or three gaps against the matching tabs.

## Milestones (implementation order)

1. `gap_rows` (all five types) + service tests.
2. Endpoint + API tests; full backend suite.
3. Frontend menu item + Vitest; full frontend suite; manual check. Update M9.md to "features complete".

## Open Questions

1. **A `SCHOOL_NO_WORKNODE` gap?** Schools with no `PartnerWorknode` mapping can't have volunteers. The Volunteers tab shows a "No Worknode found … contact an admin" state for them, and `VOLUNTEER_UNASSIGNED` can never fire for them. It's a real setup gap, but it isn't in the M9 spec. Add it as a sixth type (small, same pattern), or leave it out for now?
