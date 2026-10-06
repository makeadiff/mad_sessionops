# Feature Plan: F-M9-3 — School volunteer roster export

**Milestone doc:** `docs/milestones/M9.md` → F-M9-3
**Status:** Plan — not started
**Date:** 2026-09-27
**Depends on:** F-M9-1 (complete). F-M9-7 reuses the row builder written here.

## Overview

This adds an **Export CSV** button to a school's **Volunteers** tab. The file has one row per volunteer, with their contact details and their current slot-class assignments at this school.
- **Who is included:** the same volunteers the tab shows. That's active users whose `worknode_id` maps to this school through `PartnerWorknode`, matched by the same rule as `services/volunteers/list.py`.
- **Main uses:** contact lists, and spotting volunteers who have no assignment.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend models | None | Read only: `User`, `PartnerWorknode`, `SlotClassSectionVolunteer`, `SlotClassSection`, `Slot`, `ClassSection`, `ClassSectionSubject`, `Subject` |
| Backend services | New | `services/exports/volunteers.py`: `VOLUNTEERS_HEADER`, `volunteer_rows_for_schools(school_ids)` (shared with F-M9-7), `school_volunteer_rows(school_id)` |
| Backend API endpoints | New | `GET /api/schools/{school_id}/exports/volunteers.csv` on `school_exports_router` |
| Frontend components | Modified | `components/schools/volunteers/VolunteerListTab.tsx`: `ExportButton` in the header row |
| Frontend API | Modified | `exports.service.ts`: `exportSchoolVolunteers(schoolId)` |
| Database migrations | No | — |
| Celery tasks | No | — |
| Existing tests | Check | Volunteers tab tests (`__tests__/schools/volunteers/`) need a `vi.mock` for `exports.service`. Fix any selectors that depend on button position (the same problem hit in F-M9-2). |
| Documentation | Update | M9.md Done log, F-M9-3 tasks file |

## High-Level Design

```
VolunteerListTab (status "ok") → ExportButton → exportSchoolVolunteers(schoolId)
  → GET /api/schools/{id}/exports/volunteers.csv
      get_school_or_403 → get_active_academic_year → school_volunteer_rows(id)
      → log_export("school_volunteers", school_id, row_count) → build_csv_response
```

**Key decisions**
- **Same matching as the tab.** Volunteers are found through `PartnerWorknode(partner_id=str(school_id))` → worknode ids → `User(is_active=True, worknode_id__in=…)`, ordered by `user_display_name`. There's no role filter, because the tab doesn't have one.
- **Bulk lookups, not per-user queries.** `list_school_volunteers` runs one assignment query per volunteer. The export loads every assignment in one query and groups it in Python. The row builder takes a list of `school_ids` from the start, so F-M9-7 can reuse it unchanged.
- **What counts as an assignment.** Active `SlotClassSectionVolunteer` rows whose slot-class is active, whose slot is active, and whose slot is at this school.
  - The tab filters on the assignment row and the school only.
  - The slot-class delete cascade (M3) already soft-deletes the assignment rows, so in consistent data the counts are the same. The extra checks guard against legacy data.
- **No academic-year filter,** because the tab has none. See Open Question 1.
- **No worknode, or no volunteers:** the export returns 200 with only a header row, and the button is still shown (see Frontend).

## Low-Level Design

### Backend

**Service: `sessionops/services/exports/volunteers.py`**

```python
VOLUNTEERS_HEADER = ["user_id", "name", "email", "contact", "role", "city",
                     "slot_class_count", "assignments"]

def volunteer_rows_for_schools(school_ids: list[int]) -> dict[int, list[list]]:
    """{school_id: [row, ...]} — one row per (school, volunteer), ordered by name."""

def school_volunteer_rows(school_id: int) -> list[list]:
    return volunteer_rows_for_schools([school_id]).get(school_id, [])
```

It runs three queries, whatever the number of schools:
1. `PartnerWorknode.objects.filter(partner_id__in=[str(i) for i in school_ids])`, `values_list("partner_id", "worknode_id")`, giving `{school_id: {worknode_ids}}`.
2. `User.objects.filter(worknode_id__in=all_wids, is_active=True).order_by("user_display_name", "user_id")`, grouped by worknode.
3. `SlotClassSectionVolunteer.objects.filter(is_active=True, removed=False, volunteer_id__in=users, slot_class_section_id__is_active=True, slot_class_section_id__removed=False, slot_class_section_id__slot_id__is_active=True, slot_class_section_id__slot_id__removed=False, slot_class_section_id__slot_id__school_id__in=school_ids)`
   - with `.select_related("slot_class_section_id__slot_id", "slot_class_section_id__class_section_id__school_class_id__class_id", "slot_class_section_id__class_section_subject_id__subject_id")`
   - grouped by `(school_id, volunteer_id)`
   - ordered by day (`DAY_ORDER`) and start time

Each assignment is formatted as `"{Day} {HH:MM}-{HH:MM} · {class name} · {bucket} · {subject}"`:
- The class part is left out when the bucket has no class (M6 buckets have `school_class_id=None`).
- The bucket is `section_display_name`, falling back to `section_name`.
- The subject goes through `services/slot_classes/helpers.py::normalize_subject_display_name`.
- Assignments are joined with `"; "`.

Each row:
```
[user_id, user_display_name, email or user_login, contact, user_role, city, len(assignments), "; ".join(assignments)]
```

**API: `api/exports_api.py`**

```python
@school_exports_router.get("/{school_id}/exports/volunteers.csv",
                           response={403: ErrorResponseSchema, 404: ErrorResponseSchema})
def export_school_volunteers(request, school_id: int):
    get_school_or_403(request.auth, school_id)
    get_active_academic_year()
    rows = school_volunteer_rows(school_id)
    log_export(request.auth, "school_volunteers", school_id=school_id, row_count=len(rows))
    return build_csv_response(export_filename("volunteers", school_id), VOLUNTEERS_HEADER, rows)
```

**Schemas / migrations:** none.

### Frontend

- **`exports.service.ts`:** `exportSchoolVolunteers(schoolId)` downloads `/schools/${id}/exports/volunteers.csv`, with fallback filename `volunteers_${id}.csv`.
- **`VolunteerListTab.tsx`:** put `<ExportButton options={[{ label: "Volunteers", onExport }]} />` at the right end of the header row, after the divider line.
  - It's only shown in the `"ok"` state. In the `no_worknode` and `no_volunteers` states there's nothing to export, and the tab shows guidance instead.
  - The button isn't role-gated.
- **State / validation:** none.

## Business Rules Enforced

- **R13:** `get_school_or_403` runs before any read.
- **R4 / R6:** only active assignments at this school are listed. R6 normally means 0 or 1 per volunteer, but the format handles more (legacy data).
- **R9:** `is_active=True, removed=False` is applied at every level (the assignment, the slot-class and the slot), and users must be `is_active=True`.
- **R8:** 404 when no year is active.

## Security Review

| Concern | Handling |
|---|---|
| Auth / RBAC | JWT middleware; `get_school_or_403` (CO own, CHO worknode, admin all) |
| Input | Only the `school_id` path int |
| Personal data | Email and phone are included (D031); every export writes one audit row |
| CSV injection | Via `safe_cell`. Phone numbers starting with `+` are prefixed with `'` so Excel shows them as text, which is the intended behaviour. |

## Testing Strategy

**Backend — `tests/exports/test_f_m9_3_volunteers_export.py`**
- **Rows and assignment text:**
  - Two volunteers on the school's worknode, one assigned and one not. Expect 2 rows with counts 1 and 0, and assignment text `"Monday 10:00-11:00 · … · English"`.
  - A bucket without a class leaves the class segment out.
- **What's excluded:**
  - An inactive user is excluded.
  - A user on a different worknode is excluded.
  - A soft-deleted assignment, an inactive slot-class and an inactive slot are each not listed.
  - An assignment at another school isn't listed under this school.
- **Parity with the tab:** for each volunteer, the row's `slot_class_count` equals `list_school_volunteers`' `active_slot_class_count`, in consistent data.
- **No worknode mapping:** returns `[]`.
- **Query count:** `volunteer_rows_for_schools` with 3 schools and several volunteers stays within a fixed number of queries (`django_assert_max_num_queries(3)`).
- **API:**
  - 200 with the CSV header.
  - One `ExportLog` row (`school_volunteers`).
  - CO on another school → 403. Unknown school → 404. No active year → 404. No token → 401.

**Frontend**
- `exportSchoolVolunteers` URL test.
- `VolunteerListTab`:
  - The button is visible in the ok state and calls the service.
  - It isn't rendered in the `no_worknode` or `no_volunteers` states.

**Manual:** export a real school, check that the row count equals the tab's volunteer count badge, and open the file in Excel.

## Milestones (implementation order)

1. Service (`volunteer_rows_for_schools`, `school_volunteer_rows`) + service tests.
2. Endpoint + API tests; full backend suite.
3. Frontend service + button + Vitest; full frontend suite; manual check.

## Open Questions

1. **Academic year for assignments.** The Volunteers tab counts active assignments at the school in any year, and so does this plan, for parity. Until year progression (M5) retires old-year slots, previous-year assignments that are still active would show. Keep parity with the tab (recommended), or limit to slots in the active year?
