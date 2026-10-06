# Feature Plan: F-M9-1 — Export foundation

**Milestone doc:** `docs/milestones/M9.md` → F-M9-1
**Status:** Plan approved 2026-09-27 — not started
**Date:** 2026-09-27

## Overview

This builds the shared groundwork every M9 CSV export depends on:
- `ExportLog`, a table recording who exported what
- a CSV response builder that opens cleanly in Excel (BOM, escapes formula-like cells)
- scope and active-year helpers for exports
- two empty export routers mounted in `routes.py`
- a frontend `ExportButton` plus a fixed `api.download()`

F-M9-1 adds no export a user can see on its own. The first real export is F-M9-2. Everything here is tested in isolation so that F-M9-2..8 only need to add a row builder, an endpoint and a button.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend models | New | `ExportLog` (`models/export_log.py`), registered in `models/__init__.py` |
| Backend services | New + small refactor | New `services/exports/` (`csv_writer.py`, `audit.py`, `scope.py`). The search filter moves out of `list_schools` into `services/schools/queries.py::filter_schools_by_search`, and both callers use it. |
| Backend API endpoints | New (routers only) | `api/exports_api.py` with `school_exports_router` (mounted at `/api/schools/`) and `exports_router` (mounted at `/api/exports/`). No endpoints until F-M9-2. |
| Backend settings | Modified | `CORS_EXPOSE_HEADERS = ["Content-Disposition"]` so the browser can read the filename cross-origin (dev runs on :3000 → :8000) |
| Frontend pages | None | Buttons are placed in F-M9-2..8 |
| Frontend components | New | `components/ui/ExportButton.tsx` |
| Frontend API | Modified + New | `lib/api/client.ts::download()` fixed; new `lib/api/services/exports.service.ts` (empty typed shell + URL helpers) |
| Database migrations | Yes | One additive migration: create `export_log` |
| Celery tasks | No | Celery is not active; exports are synchronous |
| Existing tests | Should not break | `api/schools_api.py` search refactor is covered by the existing Schools list tests. `test_model_column_conventions.py` must pass. |
| Documentation | Update | `M9.md` decisions 4 and 6 already updated; still to do: `DECISIONS.md` entry for personal data + audit; add M9 to the `MILESTONE.md` overview table |

## Spec corrections (approved 2026-09-27, applied to M9.md)

1. **No active year returns 404, not 409.** The existing `services/academic_year/queries.py::get_active_academic_year()` already raises `NotFound("No active academic year is configured.")`. Reuse it rather than invent a second behaviour. This changes decision 4 and the F-M9-1 acceptance criterion.
2. **Build the file in memory rather than streaming it.**
   - With `StreamingHttpResponse`, the audit row can only be written from inside the generator, after the view has returned. It then fails silently if the client disconnects, and it runs outside request error handling and Sentry context.
   - Volumes are small: the largest export is a few thousand child rows, about 1 MB.
   - v1 therefore builds the rows as a list, writes the audit row, then returns a plain `HttpResponse`. Service functions still use `.iterator()` and bulk queries.
   - Switching to streaming later only touches `csv_writer.py`.
   - This changes decision 6.

## High-Level Design

### Data flow (as F-M9-2..8 will use it)

```
Browser: ExportButton click
  → exportsService.x()  →  api.download(url, fallbackName)       [axios, responseType: blob, Bearer token]
  → Ninja view (JWT auth via global CustomJwtAuthMiddleware)
      1. scope guard      get_school_or_403(user, id)  |  export_school_ids(user, search)
      2. year guard       get_active_academic_year()   → 404 if none
      3. rows             services/exports/<domain>.py → (header, list[rows])
      4. audit            log_export(user, type, ..., row_count=len(rows))
      5. response         build_csv_response(filename, header, rows)
  ← 200 text/csv + Content-Disposition: attachment; filename="..."
Browser: blob → object URL → <a download> click → revoke URL
```

Errors raised in steps 1–2 go through the existing Ninja exception handlers in `routes.py`, which return a JSON `{detail}` body. They occur before any CSV is built, so a failed export never writes an audit row.

### Key decisions

- **No new permission concept.** Export access equals view access (R13). This reuses `get_school_or_403` and `schools_visible_to` from `services/rbac/scope.py` unchanged.
- **One search implementation.** The partner-name/city/state search is moved out of `api/schools_api.py::list_schools` into a service helper. That keeps the CSV rows identical to the Schools list for the same search.
- **Audit on success only.** One row per 200 response. Denied and failed requests are already visible in logs and Sentry.
- **Routers are split by URL prefix.** Per-school exports sit next to other school routes (`/api/schools/{id}/exports/...`, like `holidays_router`). Cross-school exports get their own `/api/exports/` prefix.

## Low-Level Design

### Backend

**Model: `sessionops/models/export_log.py`**

```python
EXPORT_TYPES = [
    ("school_children", "School children roster"),
    ("school_volunteers", "School volunteer roster"),
    ("school_timetable", "School timetable"),
    ("schools_summary", "Schools summary"),
    ("all_children", "All children in scope"),
    ("all_volunteers", "All volunteers in scope"),
    ("gap_report", "Ops gap report"),
]

class ExportLog(models.Model):
    export_log_id = models.BigAutoField(primary_key=True)
    user_id = models.ForeignKey("sessionops.User", on_delete=models.PROTECT,
                                db_column="user_id", related_name="+")
    export_type = models.CharField(max_length=40, choices=EXPORT_TYPES, db_index=True)
    school_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # loose → partner.partner_id; null = cross-school
    filters = models.JSONField(default=dict)
    school_count = models.IntegerField(default=1)
    row_count = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "export_log"
        indexes = [models.Index(fields=["user_id", "created_at"])]
```

- The log is append-only. It has no `is_active`/`removed` columns, the same exception as `RealtimeSyncLog` and `SyncRun` (see R9 note below).
- `db_column="user_id"` is required by `test_model_column_conventions.py`.

**Migration:** `makemigrations sessionops` produces one `CreateModel`. It is additive, has no data migration and needs no backfill. It can be reversed with `migrate sessionops <prev>` because nothing references it.

**Schemas:** none. CSV responses have no Ninja response schema. Error bodies reuse `schemas/auth.py::ErrorResponseSchema` in the `response={403:…, 404:…}` declarations so OpenAPI lists them.

**Services: `sessionops/services/exports/`**

```python
# csv_writer.py
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

def safe_cell(value) -> str:
    """None → ''; date → YYYY-MM-DD; time → HH:MM; datetime → YYYY-MM-DD HH:MM (IST);
    bool → 'yes'/'no'; str starting with a FORMULA_PREFIX → "'" + value; else str(value)."""

def build_csv_response(filename: str, header: list[str], rows: list[list]) -> HttpResponse:
    """text/csv; charset=utf-8, UTF-8 BOM, CRLF (csv default), header always written.
    Content-Disposition: attachment; filename="<ascii-safe filename>"."""

def export_filename(export: str, scope: str | int) -> str:
    """'children_12345_2026-09-27.csv' / 'schools_all_2026-09-27.csv' (date in Asia/Kolkata)."""
```

```python
# audit.py
def log_export(user, export_type: str, *, row_count: int, school_id: int | None = None,
               filters: dict | None = None, school_count: int = 1) -> ExportLog
```

```python
# scope.py
def export_school_ids(user, search: str | None) -> list[int]:
    """partner_ids from schools_visible_to(user) narrowed by filter_schools_by_search; ordered by partner_name."""
```

**Refactor: `services/schools/queries.py`**

```python
def filter_schools_by_search(user, qs, search: str) -> QuerySet:
    """Exact logic currently inline in api/schools_api.py::list_schools (name | city | state icontains, distinct)."""
```

`list_schools` is changed to call it, with no behaviour change.

**API: `sessionops/api/exports_api.py`**

```python
school_exports_router = Router(tags=["Exports"])   # add_router("/api/schools/", ...)
exports_router = Router(tags=["Exports"])          # add_router("/api/exports/", ...)
```

These are registered in `routes.py` after `holidays_router`. There are no endpoints yet. F-M9-2 adds the first, `/{school_id}/exports/children.csv`.

**Settings:** add `CORS_EXPOSE_HEADERS = ["Content-Disposition"]` to `sessionops/settings.py` next to the other `CORS_*` settings.

### Frontend

- **`lib/api/client.ts::download(url, fallbackFilename, params?)`**
  - Accept `params`, passed to axios.
  - Read the filename from the `content-disposition` response header (`filename="..."`), falling back to `fallbackFilename`.
  - Build the Blob with `type: "text/csv;charset=utf-8"`.
  - Append the link to `document.body`, click it, remove it, and revoke the URL in `setTimeout(…, 0)`. The current version revokes the URL before the download has started.
  - On error, the interceptor has already rejected with `{message, code, status, data}`. With a blob response, `data` is a `Blob`, so `download()` tries to parse `await data.text()` as JSON and overwrites `message` with `detail` before re-throwing. For 403 the interceptor's generic message is kept, which is what other pages show.
- **`lib/api/services/exports.service.ts`**: `exportsService = {}` plus a `buildQuery(params)` helper. F-M9-2..8 each add one function, e.g. `schoolChildren(schoolId, status) => api.download(\`/schools/${schoolId}/exports/children.csv\`, …, { status })`.
- **`components/ui/ExportButton.tsx`** (client component)
  - Props: `options: { label: string; onExport: () => Promise<void> }[]`, `label?` (default "Export CSV"), `disabled?`.
  - With one option it renders an outlined `Button` with the `FileDownloadOutlined` icon. With several it renders a `Button` plus `Menu`.
  - While a download is running, the button shows a `CircularProgress` in place of the icon and is disabled, so it can't be double-clicked.
  - Errors are passed to `showError(err.message)` from `lib/toast/toast.tsx`.
  - MUI imports use subpaths only (frontend CLAUDE.md rule 3). Styling uses theme tokens, never hardcoded values.
- **State:** local `useState` only; no Redux.
- **Validation:** none; there are no forms.
- **RBAC display:** the button is shown to every logged-in user, because anyone who can see the page is in scope for it. The backend enforces scope.

## Business Rules Enforced

- **R13 — scope filtering by default.** Every export goes through `get_school_or_403` or `export_school_ids`, and no bypass exists.
- **R8 — exactly one active academic year.** Exports use `get_active_academic_year()` and return 404 when none is active.
- **R9 — no hard deletes.** `ExportLog` is append-only, so nothing is ever deleted. Like the sync logs, it has no soft-delete columns. Confirmed acceptable 2026-09-27.

## Security Review

| Concern | Handling |
|---|---|
| Auth | The global JWT middleware covers every export route; unauthenticated requests get 401. No `auth=None`. |
| RBAC | Per-school: `get_school_or_403` (404 for unknown school, 403 out of scope). Cross-school: `schools_visible_to`. CO, CHO and admin (including CXO) scope works exactly as on the Schools page. |
| Input validation | Only `search` (free text, used in ORM `icontains` and so parameterised) and later `status` (a `Literal` enum in Ninja) are accepted. `school_id` is an int path parameter. |
| Personal data exposure | Accepted by product decision (M9 decision 3). Mitigated by the audit trail (user, type, school, filters, count, time). There are no bulk exports beyond the user's own scope. |
| CSV/formula injection | `safe_cell` prefixes `'` on `= + - @ \t \r`. Child and volunteer names come from Hasura and CO input, so this matters. |
| Header injection | The filename is built only from the export slug, an integer `partner_id` and a date, never from user input. |
| Caching | Set `Cache-Control: no-store` on CSV responses so personal data isn't cached by proxies or the browser. |

## Testing Strategy

**Backend — `sessionops/tests/exports/test_f_m9_1_foundation.py`**
- `safe_cell`:
  - None → ''
  - date, time and datetime formats
  - `=SUM(A1)` → `'=SUM(A1)`; also `+91…`, `-5`, `@x`, and a leading tab
  - a normal string and an int unchanged
- `build_csv_response`:
  - Status 200, `text/csv; charset=utf-8`.
  - The body starts with `﻿`, uses CRLF, and always has a header even with 0 rows.
  - A Devanagari name round-trips unchanged.
  - `Content-Disposition` carries the filename; `Cache-Control: no-store` is set.
- `export_filename` produces the expected pattern and uses the IST date.
- `log_export` creates one row with the given fields.
- `export_school_ids`:
  - A CO gets only their own converted schools.
  - A CHO gets only their worknode schools.
  - An admin gets all converted schools.
  - `search` narrows by name, city or state.
  - A user with no scope gets `[]`.
  - Setup uses the local `_make_user` / `_make_school` helpers, following `test_f_m3_4_cho_scope.py`.
- `filter_schools_by_search` refactor: the existing Schools list API tests stay green, plus one new test that name, city and state search each match.
- `test_model_column_conventions.py` passes.

**Frontend — `__tests__/ui/ExportButton.test.tsx`, `__tests__/api/download.test.ts`**
- ExportButton:
  - With a single option, clicking calls `onExport`, shows the spinner while pending, and disables the button.
  - With several options, the menu lists them and clicking one calls the right handler.
  - When `onExport` rejects, `showError` is called with its message.
- `download()`:
  - Uses the `Content-Disposition` filename, or the fallback when the header is absent.
  - A JSON-in-Blob error is turned into `message = detail`.

**Manual:** skipped in F-M9-1; there's nothing for a user to see. F-M9-2 does the first end-to-end check: Excel on Windows, a Hindi name, and a matching row count.

## Milestones (implementation order)

1. **Model + migration.** `ExportLog`, the migration, and `test_model_column_conventions.py` green. The system works as before.
2. **Backend helpers.** `csv_writer.py`, `audit.py`, `scope.py`, the `filter_schools_by_search` refactor, tests, routers mounted and CORS expose header. The full backend pytest suite is green.
3. **Frontend foundation.** The `download()` fix, the `exports.service.ts` shell, `ExportButton` and Vitest. `npm run lint` and `npm run test` are green.

Each chunk leaves the system working, and none of them changes current behaviour.

## Resolved Decisions (2026-09-27)

1. **Spec corrections:** approved. No active year returns 404, and files are built in memory rather than streamed. Both are applied to M9.md.
2. **R9 and log tables:** `ExportLog` stays append-only with no soft-delete columns, like `realtime_sync_log`.
3. **Log retention:** deferred; there's no cleanup policy in M9.
4. **Milestone number:** stays M9.

No open questions remain for F-M9-1.
