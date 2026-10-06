# F-M9-1 Execution Progress

Plan: `docs/milestones/plans/F-M9-1-plan.md`. Not committing; the human commits manually.
**Status:** Complete 2026-09-27. Migration applied to dev (`mad_dev` / `mad_sessionops_dev`); staging and prod are still pending.

## Milestone 1: Model + migration
- [x] `models/export_log.py`: ExportLog + EXPORT_TYPES
- [x] Registered in `models/__init__.py`
- [x] Migration `0031_export_log.py`
- [x] `test_model_column_conventions.py` green

## Milestone 2: Backend helpers
- [x] `services/schools/queries.py::filter_schools_by_search`; `list_schools` refactored to use it
- [x] `services/exports/csv_writer.py` (`safe_cell`, `build_csv_response`, `export_filename`)
- [x] `services/exports/audit.py` (`log_export`)
- [x] `services/exports/scope.py` (`export_school_ids`)
- [x] `api/exports_api.py` (`school_exports_router`, `exports_router`), mounted in `routes.py`
- [x] `CORS_EXPOSE_HEADERS = ["Content-Disposition"]` in settings
- [x] Tests `tests/exports/test_f_m9_1_foundation.py`: 25 passed
- [x] Full backend suite: 806 passed
- [x] `makemigrations --check`: no changes; migration DB-alias check passed

## Milestone 3: Frontend foundation
- [x] `lib/api/client.ts`:
  - `download(url, fallbackFilename, params?)`: reads the Content-Disposition filename, revokes the object URL after the click, parses the JSON error blob
  - `filenameFromDisposition`
  - `ApiRejection` type
- [x] `lib/api/services/exports.service.ts`: `exportsService` shell + `exportParams`
- [x] `components/ui/ExportButton.tsx`
- [x] Vitest: `__tests__/ui/ExportButton.test.tsx`, `__tests__/api/download.test.ts`: 12 passed
- [x] Full frontend suite: 218 passed (26 files)

## Validation
- [x] RBAC: no endpoints yet. The scope helper is built on `schools_visible_to` and tested for CO, CHO, admin and no-scope users.
- [x] No business logic in views or frontend
- [x] No secrets and no `console.log`
- [ ] **Lint.** `just lint` and `npm run lint` both fail, on problems that were already there:
  - Backend: 32 ruff errors, and 160 files `ruff format --check` would reformat.
  - Frontend: 178 ESLint problems.
  - New and changed files add none: ruff check is clean, and the frontend files are clean except `client.ts`, which is back to its original 32 problems.
- [x] Docs:
  - `docs/DATA_MODEL.md` doesn't exist, so nothing to update there.
  - Updated: `DECISIONS.md` D031, `BUSINESS_RULES.md` R9 exceptions, `MILESTONE.md` M9 row and section, and the `M9.md` status and Done log.

## Deviations
- `filter_schools_by_search(qs, search)` has no `user` parameter; one `Q` filter matches the old OR of three querysets.
- `ExportButton` uses `showError(error.message)` instead of `showApiError`, because `showApiError` replaces 404 text with a generic message and would hide "No active academic year is configured." There is no toast on `SESSION_EXPIRED`.
- `download()` keeps the interceptor's generic message for 403 and 5xx, so a 500 `detail` never leaks to the user.
- The repo's ruff config (line length) doesn't match its existing code. I reverted the unrelated rewrapping in `services/schools/queries.py` and ran the formatter only on new files.

## Blockers
- None
