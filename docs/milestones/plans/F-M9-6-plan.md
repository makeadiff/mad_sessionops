# Feature Plan: F-M9-6 — All children export (in scope)

**Milestone doc:** `docs/milestones/M9.md` → F-M9-6
**Status:** Plan — not started
**Date:** 2026-09-27
**Depends on:**
- F-M9-2 (children row builder)
- F-M9-5 (the Schools toolbar Export menu, and the export-only page search `filter_schools_like_page`: name, city or CO name)

## Overview

This adds **All children** to the Schools page **Export** menu. It downloads one combined children list across every school the user can see, narrowed by the page's search box.
- **Columns:** the same as the F-M9-2 roster, with `school_id`, `school_name` and `school_city` added in front (`school_city`, not `city`, because the roster already has its own `city` column).
- **Main uses:** city-level and portfolio reporting, without exporting school by school.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend models | None | Read only |
| Backend services | Modified + New | `services/children/queries.py`: extract `annotate_current_placement(qs)`; `list_children` uses it with unchanged behaviour. `services/exports/children.py`: extract `_rows_from(qs)`; new `all_children_rows(partner_ids, status)` and `ALL_CHILDREN_HEADER`. |
| Backend API endpoints | New | `GET /api/exports/children.csv?search=&status=all` on `exports_router` |
| Frontend components | Modified | `SchoolListPage.tsx`: add the "All children" export option |
| Frontend API | Modified | `exports.service.ts`: `exportAllChildren(search)` |
| Database migrations | No | — |
| Existing tests | Must stay green | All `list_children` tests (`test_f_m2_*_children.py`, `test_f_m6_4_children.py`) and the F-M9-2 tests, since both refactors keep the same behaviour |
| Documentation | Update | M9.md Done log, tasks file |

## High-Level Design

```
SchoolListPage → Export ▸ All children → exportAllChildren(debouncedSearch)
  → GET /api/exports/children.csv?search=…&status=all
      get_active_academic_year → ids = export_school_ids(user, search)
      rows = all_children_rows(ids, status)
      log_export("all_children", school_count=len(ids), filters) → build_csv_response("children_all_…")
```

**Key decisions**
- **One query across all schools.** The placement annotations (the current section's name and display name, the current class, and the section and class ids) move into `annotate_current_placement(qs)`. Both `list_children(school_id, …)` and the new cross-school query use it, so the class and bucket come from exactly the same code.
- **Row formatting is shared.** `school_children_rows` and `all_children_rows` both go through `_rows_from(qs)`, with the same removal-log subqueries and cell mapping. The cross-school version adds the three school columns in front.
- **Status:** the Schools page has no status control, so the default is `all`. The `status` parameter is accepted (`Literal`) for API symmetry and future use.
- **Order:** school name, then class, then bucket, then first name, then last name.

## Low-Level Design

### Backend

**`services/children/queries.py`**

```python
def annotate_current_placement(qs: QuerySet[Child]) -> QuerySet[Child]:
    """The five Subquery annotations currently inline in list_children."""

def list_children(school_id, *, ...):   # unchanged signature/behaviour; uses the helper
```

**`services/exports/children.py`**

```python
ALL_CHILDREN_HEADER = ["school_id", "school_name", "school_city", *CHILDREN_HEADER]

def all_children_rows(partner_ids: list[int], *, status: str = "all") -> list[list]:
```

- The queryset is `Child.objects.filter(school_id__in=partner_ids)` with the status filter, which is the same `is_active` / `removed` logic as `list_children`.
  - The status filter moves into a small helper `_filter_status(qs, status)`, shared with `list_children`.
- It goes through `annotate_current_placement`, then the removal subqueries.
- It's ordered by class, bucket and name. The school-name ordering is applied in Python, using a `Partner` map `{partner_id: (name, city)}` from one query and a stable sort.
- An empty `partner_ids` returns `[]` without querying.

**API**

```python
@exports_router.get("children.csv")
def export_all_children(request, search: Optional[str] = None,
                        status: Literal["active", "inactive", "all"] = "all"):
    get_active_academic_year()
    ids = export_school_ids(request.auth, search)
    rows = all_children_rows(ids, status=status)
    log_export(request.auth, "all_children", school_count=len(ids),
               filters=_non_empty({"search": search, "status": status}), row_count=len(rows))
    return build_csv_response(export_filename("children", "all"), ALL_CHILDREN_HEADER, rows)
```

### Frontend

- **`exports.service.ts`:** `exportAllChildren(search?)` downloads `/exports/children.csv` with `{ search, status: "all" }`, and fallback filename `children_all.csv`.
- **`SchoolListPage.tsx`:** append `{ label: "All children", onExport: () => exportAllChildren(debouncedSearch) }` to `exportOptions`. With two or more options the button becomes a menu.

## Business Rules Enforced

- **R13:** schools come only from `export_school_ids`, which is based on `schools_visible_to`.
- **R9:** `removed=True` children are never included.
- **R10:** inactive children carry their current removal reason (from F-M9-2).
- **R8:** 404 when no year is active.

## Security Review

| Concern | Handling |
|---|---|
| Auth / RBAC | JWT. There's no `school_id` input, so scope can't be widened by crafting a request. |
| Input | `search` goes to ORM `icontains`; `status` is a `Literal` (422 otherwise) |
| Personal data | Largest export by personal data: dates of birth across every school in scope. It's covered by D031 and the audit row, which records `school_count`. |
| Volume | An admin with every school gets a few thousand rows (~1 MB), which fits the in-memory decision. Revisit only if the number of children grows by 10×. |

## Testing Strategy

**Backend — `tests/exports/test_f_m9_6_all_children_export.py`**
- **Refactor safety net:** the existing `list_children` suites and the F-M9-2 tests pass unchanged.
- **Rows and parity:**
  - 2 schools × 2 children gives 4 rows with correct school columns, ordered by school name.
  - For each school, the rows (minus the school columns) equal `school_children_rows(school, status=…)`.
- **Status:** `active` and `inactive` narrow the rows correctly.
- **Scope:**
  - A CO doesn't get another CO's children.
  - A CHO gets only their worknode schools.
  - A user with no schools gets a header-only file.
- **Search:** narrows the schools covered (name, city or CO name).
- **Query count:** constant for 2 schools versus 6.
- **API:** 200 with `children_all_{date}.csv`; an audit row with `school_id=None`, `school_count`, and `filters`; 404 when no year is active; 401 without a token; 422 for a bad status.

**Frontend**
- `exportAllChildren` params test.
- `SchoolListPage`: the Export menu lists "All children" and passes the search.

**Manual:** as an admin, export all children. Check that the sum of per-school `active_children` from F-M9-5 equals the active rows here, and open the file in Excel.

## Milestones (implementation order)

1. `annotate_current_placement` / `_filter_status` refactor, with the existing tests green.
2. `_rows_from` refactor + `all_children_rows` + endpoint + tests; full backend suite.
3. Frontend menu item + Vitest; full frontend suite; manual check.

## Open Questions

- None.
