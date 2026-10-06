# Feature Plan: F-M9-5 — Schools summary export

**Milestone doc:** `docs/milestones/M9.md` → F-M9-5
**Status:** In progress, 2026-09-27. The search design was revised during the build; see "Revision" below.
**Date:** 2026-09-27
**Depends on:** F-M9-1 (complete). F-M9-6, F-M9-7 and F-M9-8 add items to the Export menu built here.

## Overview

This adds an **Export** menu to the **Schools** list toolbar. Its first item, **Schools summary**, downloads one row per school the user can see, with the key operational counts.
- **Rows included:** the schools the page's search box currently shows.
- **Main uses:** the weekly ops review and city-level reporting.

## Decision taken during planning (2026-09-27)

**The backend school search changes to match the UI.**
- The Schools page filters in the browser on **name, city or CO name** (`SchoolListPage.tsx::visibleSchools`).
- The backend helper `services/schools/queries.py::filter_schools_by_search` (from F-M9-1) matches **name, city or state**.
- Following the user's choice, the helper now matches name, city or CO name, so every Schools-page export (F-M9-5 to F-M9-8) matches the screen.

Two more details, for exact parity with the page:
- **No trimming.** The helper skips the filter when the search is blank after trimming, but otherwise matches the raw text, just as the page does (`if (debouncedSearch.trim())`, then match the untrimmed value).
- **Nothing on screen changes.** The page never sends `search` to `GET /schools/` (it filters locally), so the API's search semantics change without any visible effect.

`M9.md` decision 9 gets updated to match.

## Revision (2026-09-27, during the build): exports get their own search

**Why the plan changed:** M1's documented test **TC-M1-4-06** ("search filters by state", in `tests/features/m1/test_f_m1_4_school_list.py`) requires `GET /api/schools/?search=` to match state. Changing the shared helper would have broken that M1 requirement.

**What the user decided:**
- `services/schools/queries.py::filter_schools_by_search` stays exactly as M1 specifies (name, city or state, trimmed). `list_schools` is unchanged.
- A new **export-only** helper, `services/exports/scope.py::filter_schools_like_page(qs, search)`, matches **name, city or CO name** with the page's trimming rule: no filter when the text is blank after trimming, otherwise the raw text is matched.
- `export_school_ids` uses the new helper, so every Schools-page export (F-M9-5 to F-M9-8) still matches the screen exactly.

**What this replaces below:** read every mention of changing `filter_schools_by_search` (state → CO name) as "add `filter_schools_like_page` in `services/exports/scope.py`". The M1 tests and `list_schools` aren't touched.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend models | None | Read only: `Partner`, `Child`, `SchoolClass`, `ClassSection`, `Slot`, `SlotClassSection`, `SchoolSessionDetails`, `PartnerWorknode`, `User` |
| Backend services | Modified + New | Modified in `services/schools/queries.py`: `filter_schools_by_search` (state → co_name, no trimming), and new `get_chos_for_schools(partner_ids)` with `get_chos_for_school` rewritten on top of it. New `services/exports/schools.py`: `SCHOOLS_HEADER`, `schools_summary_rows(partner_ids)`. |
| Backend API endpoints | New + behaviour change | New `GET /api/exports/schools.csv?search=` on `exports_router`. `GET /api/schools/?search=` now matches CO name instead of state; no current caller uses it. |
| Frontend components | Modified | `components/schools/SchoolToolbar.tsx`: `exportOptions` prop and an `ExportButton` labelled "Export". `SchoolListPage.tsx` passes the options, with the current search. |
| Frontend API | Modified | `exports.service.ts`: `exportSchoolsSummary(search)` |
| Database migrations | No | — |
| Existing tests | Update | `tests/exports/test_f_m9_1_foundation.py`: the state-search tests become CO-name tests. Schools list API tests that rely on search by state need checking (grep first). `__tests__/schools/SchoolListPage.test.tsx` needs a `vi.mock` for `exports.service`. |
| Documentation | Update | M9.md decision 9 and the F-M9-5 search note, Done log, tasks file |

## High-Level Design

```
SchoolListPage (debouncedSearch) → SchoolToolbar → ExportButton menu → "Schools summary"
  → exportSchoolsSummary(search) → GET /api/exports/schools.csv?search=…
      get_active_academic_year()
      ids = export_school_ids(user, search)          # schools_visible_to ∩ search, ordered by name
      rows = schools_summary_rows(ids)
      log_export("schools_summary", school_id=None, school_count=len(ids), filters={search})
      build_csv_response(export_filename("schools", "all"), SCHOOLS_HEADER, rows)
```

**Key decisions**
- **Scope comes from `export_school_ids`** (F-M9-1), so CO, CHO and admin scope are identical to the Schools page.
- **Counts are the page's counts.** `active_children`, `volunteers`, `classes`, `slot_classes` and `academic_year` come straight from `get_school_stats`. The extra columns are bulk grouped queries. No query runs per school.
- **Bulk CHO names.** `get_chos_for_schools(partner_ids) -> dict[int, list[User]]` does the same worknode matching and `parse_user_roles` CHO check in 2 queries. `get_chos_for_school(id)` becomes `get_chos_for_schools([id]).get(id, [])`, so behaviour doesn't change.

## Low-Level Design

### Backend

**`services/schools/queries.py`**

```python
def filter_schools_by_search(qs, search):
    if not (search or "").strip():
        return qs
    return qs.filter(Q(partner_name__icontains=search) | Q(city__icontains=search)
                     | Q(co_name__icontains=search)).distinct()

def get_chos_for_schools(partner_ids: list[int]) -> dict[int, list[User]]: ...
```

**Service: `services/exports/schools.py`**

```python
SCHOOLS_HEADER = ["partner_id", "school_name", "city", "state", "co_name", "cho_names",
                  "academic_year", "active_children", "inactive_children", "volunteers",
                  "classes", "buckets", "slots", "slot_classes", "term_start", "term_end",
                  "mou_start_date", "mou_end_date"]

def schools_summary_rows(partner_ids: list[int]) -> list[list]:
```

It runs a constant number of queries:
- `Partner.objects.filter(partner_id__in=ids)`, keyed by id. Output keeps the `partner_ids` order (by name).
- `get_school_stats(ids)`
- **Inactive children:** `Child(is_active=False, removed=False)` grouped by `school_id`.
- **Buckets:** `ClassSection(is_active=True, removed=False)` grouped by `school_id`, the same set as `list_buckets_for_school`.
- **Slots:** `Slot(is_active=True, removed=False)` grouped by `school_id`.
- **Term dates:** `SchoolSessionDetails(school_academic_year__academic_year_id=active_year, is_active=True, removed=False)`, as `{school_id: (start_date, end_date)}`. This is the same filter as `services/sessions/queries.py::get_active_session`.
- **CHO names:** `get_chos_for_schools(ids)`, joined with `"; "`.

**API**

```python
@exports_router.get("schools.csv")
def export_schools_summary(request, search: Optional[str] = None):
    get_active_academic_year()
    ids = export_school_ids(request.auth, search)
    rows = schools_summary_rows(ids)
    log_export(request.auth, "schools_summary", school_count=len(ids),
               filters=_non_empty({"search": search}), row_count=len(rows))
    return build_csv_response(export_filename("schools", "all"), SCHOOLS_HEADER, rows)
```

This mounts at `/api/exports/` + `schools.csv`. Confirm while building how Ninja joins the router prefix and path, and add a slash if needed.

### Frontend

- **`exports.service.ts`:** `exportSchoolsSummary(search?)` downloads `/exports/schools.csv` with params `{ search }`, and fallback filename `schools_all.csv`.
- **`SchoolToolbar.tsx`:**
  - New optional prop `exportOptions?: ExportOption[]`.
  - When it's present, render `<ExportButton label="Export" options={exportOptions} />` after the Sort button.
  - With only one option it shows as a plain button; F-M9-6 to F-M9-8 add more, which turns it into a menu.
- **`SchoolListPage.tsx`:** passes `exportOptions={[{ label: "Schools summary", onExport: () => exportSchoolsSummary(debouncedSearch) }]}`. The toolbar only renders when the user has schools, so users with none never see the button.

## Business Rules Enforced

- **R13:** `schools_visible_to` via `export_school_ids`. CXO counts as admin scope, the same as the page.
- **R9:** active and non-removed filters on every count.
- **R8:** 404 when no year is active. Term dates are read for the active year only.

## Security Review

| Concern | Handling |
|---|---|
| Auth / RBAC | JWT middleware. Scope comes only from `schools_visible_to`, and there's no `school_id` input to tamper with. |
| Input | `search` is used in ORM `icontains`, so it's parameterised |
| Personal data | School contact data isn't exported. Names of the CO and CHOs are included (staff, already visible in the app). |
| CSV injection | `safe_cell` |

## Testing Strategy

**Backend — `tests/exports/test_f_m9_5_schools_export.py`**
- **Row values:**
  - Admin with 3 schools gets 3 rows, ordered by name.
  - `active_children`, `volunteers` and `classes` equal `get_school_stats` for each school.
  - `inactive_children`, `buckets`, `slots` and `slot_classes` are correct.
- **Term dates:** present for the active year. They're empty when none exist, or when they only exist for another year.
- **CHO names:** listed for a school whose worknode has CHO users. Users without the CHO role aren't listed.
- **Scope:**
  - A CO sees only their own schools, and a CHO only their worknode schools.
  - A CO with no schools gets a header-only file.
- **Search:** matches name, city and CO name, and no longer matches state. Search `"pune "` (trailing space) matches only what the page would match.
- **Query count:** constant for 3 schools versus 10 (`django_assert_max_num_queries`).
- **`get_chos_for_schools`:** returns the same result as the old per-school `get_chos_for_school`. The existing school detail tests still pass.
- **API:**
  - 200, filename `schools_all_{date}.csv`.
  - `ExportLog` has `school_id=None`, `school_count`, and `filters` equal to `{"search": …}` only when search is set.
  - No active year → 404. No token → 401.

**Frontend**
- `exportSchoolsSummary` URL and params test.
- `SchoolToolbar`: renders Export when `exportOptions` is given, and doesn't when it's absent.
- `SchoolListPage`: typing a search and then exporting passes the debounced value.

**Manual:** as an admin and as a CO, search "pune", export, and check the row count equals the number of visible cards and the counts match the cards.

## Milestones (implementation order)

1. Search change + `get_chos_for_schools` refactor + tests (existing suites stay green).
2. `schools_summary_rows` + endpoint + tests; full backend suite.
3. Toolbar Export menu + page wiring + Vitest; full frontend suite; manual check.

## Open Questions

- None beyond the search decision recorded above.
