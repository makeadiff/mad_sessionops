# Feature Plan: F-M9-2 — School children roster export

**Milestone doc:** `docs/milestones/M9.md` → F-M9-2
**Status:** Plan approved 2026-09-27 — not started
**Date:** 2026-09-27
**Depends on:** F-M9-1 (complete)

## Overview

This adds the first export users can see: an **Export CSV** button on a school's **Children** tab that downloads the children in the current view.
- **What it follows:** the tab's current filters (search, class, bucket or "unassigned", and status).
- **What's in the file:** class and bucket placement, plus the removal reason, details and date for inactive children.
- **How it's built:** it reuses `list_children`, which already does the filtering and adds the class and section names. That keeps the file consistent with the tab's "N results" count.

## Decision taken during planning (2026-09-27)

**Export exactly what's on screen.** The M9 spec said only the status filter would apply. The user chose to apply every filter the tab has: search, class, bucket or unassigned, and status. `list_children` already supports all of them, so there's no extra backend work. M9.md F-M9-2 and decision 9 have been updated to match.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend models | None | Read only: `Child`, `ChildClass`, `ChildClassSection`, `ChildRemovalLog`, `REMOVED_REASONS` |
| Backend services | New | `services/exports/children.py::school_children_rows`. `services/children/queries.py::list_children` is reused unchanged. |
| Backend API endpoints | New | `GET /api/schools/{school_id}/exports/children.csv` on `school_exports_router` (`api/exports_api.py`) |
| Frontend pages | None | School detail → Children tab (existing route) |
| Frontend components | Modified | `components/schools/children/ChildrenTab.tsx`: `ExportButton` in the page header |
| Frontend API | Modified | `lib/api/services/exports.service.ts`: `schoolChildren()`. `exportParams` gains boolean support. |
| Database migrations | No | — |
| Celery tasks | No | — |
| Existing tests | Update | `__tests__/schools/children/ChildrenTab.test.tsx`: add a `vi.mock` for `exports.service`. There's no backend impact because `list_children` is unchanged. |
| Documentation | Update | M9.md (F-M9-2 filters, decision 9, Done log) and the F-M9-2 tasks file |

## High-Level Design

### Data flow

```
ChildrenTab (status, debouncedSearch, classId, bucketFilter)
  → ExportButton → exportsService.schoolChildren(schoolId, filters)
  → api.download("/schools/{id}/exports/children.csv", "children_{id}.csv", params)
  → export_school_children view
      get_school_or_403(user, school_id)        # 404 unknown school, 403 out of scope
      get_active_academic_year()                # 404 if none (F-M9-1 decision)
      rows = school_children_rows(school_id, filters)
      log_export(user, "school_children", school_id=…, filters=<non-empty filters>, row_count=len(rows))
      build_csv_response(export_filename("children", school_id), CHILDREN_HEADER, rows)
  ← text/csv attachment children_{partner_id}_{YYYY-MM-DD}.csv
```

### Key decisions

- **One source of truth for filtering.** The export calls `list_children` with the same arguments as the tab's own request (`GET /schools/{id}/children/`). Filtering logic is never re-implemented.
- **Status is sent explicitly.** The tab loads `status=all` and filters status in the browser. The export sends the selected `status` to the server, and `list_children` applies the same `is_active` / `removed` logic.
- **Removal info comes from the current removal log.** `deactivate_child` writes a `ChildRemovalLog` row with `is_active=True, removed=False`, and `reactivate_child` marks it inactive. So an inactive child's current reason is the newest active log row, ordered by `-removed_datetime`. The partner-deactivation cascade (R17) writes "other" with the details "School dropped from CRM", which also shows correctly.
- **Sort order is class → bucket → first name → last name,** as the spec asks (useful for printing). The tab sorts by name only, so the rows are the same but the order differs.

## Low-Level Design

### Backend

**Models / migrations:** none.

**Service: `sessionops/services/exports/children.py`**

```python
CHILDREN_HEADER = [
    "child_id", "first_name", "last_name", "gender", "date_of_birth", "age",
    "class", "bucket", "status", "date_of_enrollment", "mad_joining_date",
    "mother_tongue", "city", "removed_reason", "removal_details", "removed_on",
]

def school_children_rows(
    school_id: int,
    *,
    status: str = "all",
    search: str | None = None,
    class_id: int | None = None,
    section_id: int | None = None,
    unassigned: bool = False,
) -> list[list]:
    """Rows for the Children-tab export. Filters are passed straight through
    to list_children so the file matches the tab."""
```

- `qs = list_children(school_id, status=…, search=…, class_id=…, section_id=…, unassigned=…)`
- Removal info is added with three `Subquery` annotations on `ChildRemovalLog.objects.filter(child_id=OuterRef("pk"), is_active=True, removed=False).order_by("-removed_datetime")`, taking `removed_reason`, `other_details` and `removed_datetime` (`[:1]`).
- `.order_by("current_class_name", "current_section_display_name", "current_section_name", "first_name", "last_name", "child_id")`. Postgres sorts NULLs last in ascending order, so unplaced children come last.
- Per row:
  - `gender` uses the display label (`get_gender_display()`).
  - `bucket` is `current_section_display_name`, falling back to `current_section_name`.
  - `status` is `"active"` or `"inactive"` (from `is_active`).
  - The removal columns are filled **only when inactive**. `removed_reason` is mapped through `dict(REMOVED_REASONS)`, falling back to the raw value for migrated or legacy codes.
  - `removed_on` is `removed_datetime`, which `safe_cell` renders in IST.
  - `None` values become empty cells through `safe_cell`.
- Queries: one for the list, with every annotation done as a subquery. There are no per-row queries.

**API: `sessionops/api/exports_api.py`**

```python
@school_exports_router.get(
    "/{school_id}/exports/children.csv",
    response={403: ErrorResponseSchema, 404: ErrorResponseSchema},
)
def export_school_children(
    request,
    school_id: int,
    status: Literal["active", "inactive", "all"] = "all",
    search: Optional[str] = None,
    class_id: Optional[int] = None,
    section_id: Optional[int] = None,
    unassigned: bool = False,
):
    get_school_or_403(request.auth, school_id)
    get_active_academic_year()
    filters = {"status": status, "search": search, "class_id": class_id,
               "section_id": section_id, "unassigned": unassigned or None}
    rows = school_children_rows(school_id, status=status, search=search,
                                class_id=class_id, section_id=section_id, unassigned=unassigned)
    log_export(request.auth, "school_children", school_id=school_id,
               filters={k: v for k, v in filters.items() if v not in (None, "")},
               row_count=len(rows))
    return build_csv_response(export_filename("children", school_id), CHILDREN_HEADER, rows)
```

The view stays thin: guard, service, audit, response. Ninja passes a returned `HttpResponse` through unchanged. Declaring 403 and 404 in `response=` documents the error bodies in OpenAPI. Declaring a 200 schema isn't needed, but confirm while building that Ninja doesn't try to validate the `HttpResponse` against one.

**Schemas:** none new. `status` is a `Literal`, so Ninja returns 422 for other values.

### Frontend

- **`lib/api/services/exports.service.ts`**
  - `exportParams` accepts `boolean`: `true` is sent as `"true"`, and `false` is dropped.
  - New type `ChildrenExportFilters = { status: "active" | "inactive" | "all"; search?: string; classId?: number | null; sectionId?: number | null; unassigned?: boolean }`.
  - New function `schoolChildren(schoolId, f)`:
    ```ts
    api.download(`/schools/${schoolId}/exports/children.csv`, `children_${schoolId}.csv`,
      exportParams({ status: f.status, search: f.search, class_id: f.classId,
                     section_id: f.sectionId, unassigned: f.unassigned }))
    ```
- **`components/schools/children/ChildrenTab.tsx`**
  - In the page header's right side, put `<ExportButton options={[{ label: "Children", onExport }]} disabled={loading || loadError} />` before "Enroll Child", in a flex `Box` with a gap.
  - `onExport` maps the tab's state: `bucketFilter === "unassigned"` becomes `unassigned: true`, a number becomes `sectionId`, and `"all"` sends neither. `search` is `debouncedSearch`, the value actually applied to the list.
  - The button is shown whether or not the user has `canModify`, because exporting is a view-level action.
- **State:** none added. The button reads the tab's existing filter state.
- **Validation:** none (no form).

## Business Rules Enforced

- **R13 — scope.** `get_school_or_403` runs before any data is read. An unknown school returns 404 and an out-of-scope school returns 403. Neither writes an audit row.
- **R9 — soft delete.** `list_children` always excludes `removed=True`, including for `status=all`. Removal-log rows are read only if `is_active=True, removed=False`.
- **R10 — removal reason.** Inactive children carry the reason recorded when they were deactivated. Reactivated children have no active log, so their removal columns are empty.
- **R8 — active academic year.** The export returns 404 when no year is active. Note that the Children tab itself doesn't require an active year (see Open Question 1).

## Security Review

| Concern | Handling |
|---|---|
| Auth | Global JWT middleware; returns 401 without a token |
| RBAC | `get_school_or_403`. CO: own schools. CHO: worknode schools. Admin and CXO: all. |
| Input validation | `status` is a `Literal`; `class_id` and `section_id` are ints. `search` goes to an ORM `icontains`, so it's parameterised. The IDs are only applied inside this school's queryset (`Child.school_id=school_id`), so an ID from another school can only narrow the results to nothing, never leak rows. |
| Personal data | Date of birth and names are included (D031), and every export writes one `ExportLog` row. |
| CSV injection | Every cell goes through `safe_cell`. Names and `other_details` are user-entered free text, so this matters. |
| Caching | `Cache-Control: no-store` (from F-M9-1) |

## Testing Strategy

**Backend service — `sessionops/tests/exports/test_f_m9_2_children_export.py`**

Setup uses the local helpers (user, partner, active year, school class, bucket) and real `enroll_child` / `deactivate_child` calls, following `test_f_m2_10_children.py`.
- Three active children and one inactive:
  - `status=all` → 4 rows.
  - `status=active` → 3 rows.
  - `status=inactive` → 1 row, with the reason label, details and date.
- A `removed=True` child never appears, even with `status=all`.
- A child with a class but no bucket has an empty bucket cell. `unassigned=True` returns only those children.
- `class_id` and `section_id` narrow the rows the same way `list_children` does. For the same filters, the row count equals `list_children(...).count()`.
- `search` matches first or last name.
- A child deactivated then reactivated is active, with empty removal columns.
- A legacy or unknown `removed_reason` code falls back to the raw value.
- Ordering: class, then bucket, then first name, with unplaced children last.
- The header equals `CHILDREN_HEADER`.

**Backend API (same file)**
- 200 response with the `text/csv` content type, `Content-Disposition` `children_{id}_{date}.csv`, and a body that parses back to the header plus the expected rows.
- `ExportLog`: one row with `export_type=school_children`, `school_id`, the correct `row_count`, and `filters` containing only the non-empty values.
- A CO exporting another CO's school gets 403 and no log row. An unknown school gets 404 and no log row.
- No active academic year → 404 and no log row.
- `status=bogus` → 422.
- No token → 401.

**Frontend**
- **`__tests__/api/download.test.ts`** (or a new `exports.service` test):
  - `schoolChildren` builds the right URL and params: `unassigned` is sent as `"true"` when set, and empty search and null IDs are dropped.
- **`__tests__/schools/children/ChildrenTab.test.tsx`:**
  - Mock `@/lib/api/services/exports.service`.
  - Clicking Export calls `schoolChildren` with the current filters (status tab, class, bucket, "unassigned").
  - The button is present even with `canModify=false`.

**Manual**
- Run the backend and frontend, and log in as a CO.
- Open a school, go to the Children tab, and set filters. Export and open the file in Excel.
- Check that:
  - the number of rows equals "N results"
  - Hindi names display correctly
  - an inactive child shows a reason
  - one `export_log` row was written

## Milestones (implementation order)

1. **Backend service + tests:** `school_children_rows` and service tests. There's no user-visible change yet.
2. **Endpoint + API tests:** the route on `school_exports_router`. Full backend suite green.
3. **Frontend:** `schoolChildren` service, the ChildrenTab button, and Vitest updates. Full frontend suite green. Then the manual check.

Each step leaves the app working.

## Resolved Decisions (2026-09-27)

1. **Filters:** the export applies everything on screen (search, class, bucket or unassigned, status).
2. **Active academic year:** kept. The export returns 404 when no year is active, the same as every other M9 export.
3. **`age` column:** the stored `age` value, as the tab shows it.

No open questions remain for F-M9-2.
