# Feature Plan: F-M9-4 — School timetable export

**Milestone doc:** `docs/milestones/M9.md` → F-M9-4
**Status:** Plan — not started
**Date:** 2026-09-27
**Depends on:** F-M9-1 (complete)

## Overview

This adds an **Export CSV** button to a school's **Slots** tab that downloads the weekly timetable, with one row per slot-class.
- **Columns:** day, time, class, bucket, subject, the assigned volunteers, and the number of children in the bucket.
- **Empty slots:** a slot with nothing scheduled in it still gets a row, so gaps are visible.
- **Main use:** printing the timetable and sharing it with the school.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend models | None | Read only: `Slot`, `SlotClassSection`, `SlotClassSectionVolunteer`, `ClassSection`, `ClassSectionSubject`, `Subject`, `ChildClassSection` |
| Backend services | New | `services/exports/timetable.py`: `TIMETABLE_HEADER`, `school_timetable_rows(school_id)` |
| Backend API endpoints | New | `GET /api/schools/{school_id}/exports/timetable.csv` |
| Frontend components | Modified | `components/schools/slots/SlotListTab.tsx`: `ExportButton` in the header actions, before the view toggle |
| Frontend API | Modified | `exports.service.ts`: `exportSchoolTimetable(schoolId)` |
| Database migrations | No | — |
| Existing tests | Check | Slot tab tests (`__tests__/schools/slots/`) need a `vi.mock` for `exports.service`. Fix any selectors that depend on button position. |
| Documentation | Update | M9.md Done log, F-M9-4 tasks file |

## High-Level Design

```
SlotListTab → ExportButton → exportSchoolTimetable(schoolId)
  → GET /api/schools/{id}/exports/timetable.csv
      get_school_or_403 → get_active_academic_year → school_timetable_rows(id)
      → log_export("school_timetable") → build_csv_response
```

**Key decisions**
- **A dedicated bulk query, not `get_school_schedule`.** The spec allowed either. `services/slot_classes/schedule.py::get_school_schedule` doesn't fit, for three reasons:
  - It runs one child-count query per slot-class.
  - It runs its own permission check.
  - It doesn't return the class name.

  The export instead reuses the pieces of its logic that fit: `normalize_subject_display_name`, and the same active filters on slots, slot-classes and assignments.
- **Same slots as the Slots tab:**
  - Every active slot at the school (`services/slots/create.py::list_slots`), with no year filter.
  - Sorted by `DAY_ORDER`, then start time, then class name, then bucket name.
- **Empty slots get one row,** with blank class, bucket and subject cells and `volunteer_count = 0`.

## Low-Level Design

### Backend

**Service: `sessionops/services/exports/timetable.py`**

```python
TIMETABLE_HEADER = ["day", "slot_name", "start_time", "end_time", "class", "bucket",
                    "subject", "volunteers", "volunteer_count", "children_in_bucket"]

def school_timetable_rows(school_id: int) -> list[list]:
```

It runs four queries, whatever the number of slots:
1. `Slot.objects.filter(school_id=…, is_active=True, removed=False)`, sorted in Python by `(DAY_ORDER[day], start_time)`.
2. `SlotClassSection.objects.filter(slot_id__in=slots, is_active=True, removed=False)`, with `.select_related("class_section_id__school_class_id__class_id", "class_section_subject_id__subject_id")`.
3. `SlotClassSectionVolunteer.objects.filter(slot_class_section_id__in=scs, is_active=True, removed=False).select_related("volunteer_id")`, grouped by slot-class, with names sorted.
4. `ChildClassSection.objects.filter(class_section_id__in=section_ids, is_active=True, removed=False)` with `.values("class_section_id").annotate(Count)`, giving `{section_id: count}`.

Each row:
- `day`: the display label from `DAYS_OF_WEEK` (e.g. "Monday").
- `slot_name`
- `start_time`, `end_time`: formatted `HH:MM` by `safe_cell`.
- `class`: the class name if the bucket has a class, otherwise empty.
- `bucket`: display name, falling back to the section name.
- `subject`: normalised.
- `volunteers`: `user_display_name`s joined with `"; "`.
- `volunteer_count`
- `children_in_bucket`

**API**

```python
@school_exports_router.get("/{school_id}/exports/timetable.csv",
                           response={403: ErrorResponseSchema, 404: ErrorResponseSchema})
def export_school_timetable(request, school_id: int):
    get_school_or_403(request.auth, school_id)
    get_active_academic_year()
    rows = school_timetable_rows(school_id)
    log_export(request.auth, "school_timetable", school_id=school_id, row_count=len(rows))
    return build_csv_response(export_filename("timetable", school_id), TIMETABLE_HEADER, rows)
```

**Schemas / migrations:** none.

### Frontend

- **`exports.service.ts`:** `exportSchoolTimetable(schoolId)` downloads `/schools/${id}/exports/timetable.csv`, with fallback filename `timetable_${id}.csv`.
- **`SlotListTab.tsx`:** add `<ExportButton options={[{ label: "Timetable", onExport }]} disabled={loading} />` as the first item in the header's action `Box`, before the agenda/grid toggle.
  - It's shown for all viewers, whatever `canModify` is.
  - It's disabled while loading. When there are no slots, it's disabled too, since the file would contain only a header.

## Business Rules Enforced

- **R13:** `get_school_or_403`.
- **R9:** active and non-removed filters on slots, slot-classes, assignments and child placements.
- **R7:** no overlapping slots per day. This isn't re-checked, only reflected: ordering by start time gives a clean day view.
- **R2 (as superseded by M6):** each slot-class has 1–5 volunteers, bounded by the bucket's children. The export reports the actual `volunteer_count` and `children_in_bucket` so ops can spot violations. It doesn't enforce anything.
- **R8:** 404 when no year is active.

## Security Review

| Concern | Handling |
|---|---|
| Auth / RBAC | JWT + `get_school_or_403` |
| Input | Only the `school_id` path int |
| Personal data | Volunteer names only (no contact details) |
| CSV injection | `safe_cell` |

## Testing Strategy

**Backend — `tests/exports/test_f_m9_4_timetable_export.py`**
- **Row counts and ordering:**
  - 2 slots (Tuesday 10:00, Monday 14:00) × 2 slot-classes = 4 rows.
  - Monday comes first, and within a slot, rows are ordered by class and bucket.
- **Empty slot:** 1 row with blank class, bucket and subject, and `volunteer_count = 0`.
- **Volunteer columns:** names are joined and sorted, and the count is correct. A soft-deleted assignment isn't counted.
- **Children and buckets:** `children_in_bucket` equals the number of active `ChildClassSection` rows. A bucket without a class has a blank class cell.
- **Excluded rows:** inactive slots and inactive slot-classes don't appear.
- **Parity:** the slot-classes and volunteers match `get_school_schedule` for the same school.
- **Query count:** the number of queries doesn't grow with the number of slots (`django_assert_max_num_queries(4)`).
- **API:** 200 with the CSV and one `ExportLog` row (`school_timetable`); 403, 404, no-active-year 404, and 401.

**Frontend**
- `exportSchoolTimetable` URL test.
- `SlotListTab`: the button is rendered and calls the service; it's disabled when there are no slots.

**Manual:** export a school with a real timetable, then print or preview it in Excel, and check the day and time order against the Slots tab.

## Milestones (implementation order)

1. Service + service tests.
2. Endpoint + API tests; full backend suite.
3. Frontend + Vitest; full frontend suite; manual check.

## Open Questions

- None. The choice between a flat query and `get_school_schedule` is already allowed by the spec, and the year behaviour matches the Slots tab, the same as F-M9-3.
