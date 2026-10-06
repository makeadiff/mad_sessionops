# Feature Plan: F-M9-7 — All volunteers export (in scope)

**Milestone doc:** `docs/milestones/M9.md` → F-M9-7
**Status:** Plan — not started
**Date:** 2026-09-27
**Depends on:**
- F-M9-3 (`volunteer_rows_for_schools`)
- F-M9-5 (the Schools toolbar Export menu, and the export-only page search `filter_schools_like_page`)

## Overview

This adds **All volunteers** to the Schools page **Export** menu. It downloads one combined volunteer list, with contact details and slot-class assignments, across every school in the user's scope, narrowed by the search box.
- **Columns:** the same as the F-M9-3 roster, with `school_id`, `school_name` and `school_city` added in front (`school_city`, not `city`, because the roster already has its own `city` column).
- **Shared worknodes:** a volunteer whose worknode maps to several schools appears once under each of them, the same as each school's Volunteers tab.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend models | None | Read only |
| Backend services | New | `services/exports/volunteers.py`: `ALL_VOLUNTEERS_HEADER`, `all_volunteer_rows(partner_ids)`, built on F-M9-3's `volunteer_rows_for_schools` |
| Backend API endpoints | New | `GET /api/exports/volunteers.csv?search=` on `exports_router` |
| Frontend components | Modified | `SchoolListPage.tsx`: add the "All volunteers" export option |
| Frontend API | Modified | `exports.service.ts`: `exportAllVolunteers(search)` |
| Database migrations | No | — |
| Existing tests | None affected | — |
| Documentation | Update | M9.md Done log, tasks file |

## High-Level Design

```
SchoolListPage → Export ▸ All volunteers → exportAllVolunteers(debouncedSearch)
  → GET /api/exports/volunteers.csv?search=…
      get_active_academic_year → ids = export_school_ids(user, search)
      rows = all_volunteer_rows(ids)
      log_export("all_volunteers", school_count=len(ids)) → build_csv_response("volunteers_all_…")
```

**Key decisions**
- **No new matching logic.** F-M9-3's `volunteer_rows_for_schools(school_ids)` was built for several schools from the start: 3 queries whatever the number of schools, keyed `{school_id: rows}`. F-M9-7 only adds the school columns and the ordering.
- **One row per (school, volunteer).** This was resolved in the M9 Day-1 check and matches the tab. Assignments are listed per school, so a volunteer shown under school A lists only their slot-classes at school A.
- **Order:** school name, then volunteer name, following the `export_school_ids` order.

## Low-Level Design

### Backend

```python
ALL_VOLUNTEERS_HEADER = ["school_id", "school_name", "school_city", *VOLUNTEERS_HEADER]

def all_volunteer_rows(partner_ids: list[int]) -> list[list]:
    if not partner_ids:
        return []
    partners = {p.partner_id: p for p in Partner.objects.filter(partner_id__in=partner_ids)}
    by_school = volunteer_rows_for_schools(partner_ids)
    return [[pid, partners[pid].partner_name, partners[pid].city, *row]
            for pid in partner_ids for row in by_school.get(pid, [])]
```

**API**

```python
@exports_router.get("volunteers.csv")
def export_all_volunteers(request, search: Optional[str] = None):
    get_active_academic_year()
    ids = export_school_ids(request.auth, search)
    rows = all_volunteer_rows(ids)
    log_export(request.auth, "all_volunteers", school_count=len(ids),
               filters=_non_empty({"search": search}), row_count=len(rows))
    return build_csv_response(export_filename("volunteers", "all"), ALL_VOLUNTEERS_HEADER, rows)
```

### Frontend

- **`exports.service.ts`:** `exportAllVolunteers(search?)` downloads `/exports/volunteers.csv`, with fallback filename `volunteers_all.csv`.
- **`SchoolListPage.tsx`:** append `{ label: "All volunteers", onExport: () => exportAllVolunteers(debouncedSearch) }`.

## Business Rules Enforced

- **R13:** scope via `export_school_ids`.
- **R4:** one volunteer belongs to exactly one school. In practice, worknode sharing (one chapter covering several schools) breaks this in the data. The export reports what the tabs show, and doesn't de-duplicate.
- **R6:** assignments are active only and listed per school.
- **R9, R8:** as in F-M9-3.

## Security Review

| Concern | Handling |
|---|---|
| Auth / RBAC | JWT; no `school_id` input |
| Input | `search` goes to ORM `icontains` |
| Personal data | Emails and phone numbers across the user's scope (D031); audit row with `school_count` |

## Testing Strategy

**Backend — `tests/exports/test_f_m9_7_all_volunteers_export.py`**
- **Grouping:** 2 schools with different worknodes put each volunteer under the right school, ordered by school name then volunteer name.
- **Shared worknode:**
  - The volunteer appears under both schools.
  - An assignment at school A appears only in the school A row.
- **Parity:** for each school, the rows (minus the school columns) equal `school_volunteer_rows(school)`.
- **Scope and search:**
  - A CHO gets only their worknode schools, and a CO only their own.
  - Search narrows the schools covered.
- **Empty scope:** no schools gives a header-only file.
- **Query count:** constant for 2 schools versus 6.
- **API:** 200 with `volunteers_all_{date}.csv`; an audit row with `school_id=None` and `school_count`; 404 when no year is active; 401 without a token.

**Frontend**
- `exportAllVolunteers` params test.
- `SchoolListPage`: the menu item is present and passes the search.

**Manual:** as an admin, export all volunteers, and compare a few schools' rows with their Volunteers tabs.

## Milestones (implementation order)

1. `all_volunteer_rows` + endpoint + tests; full backend suite.
2. Frontend menu item + Vitest; full frontend suite; manual check.

## Open Questions

- Inherits F-M9-3's Open Question 1 (academic-year filtering of assignments). Whatever is decided there applies here automatically, because the row builder is shared.
