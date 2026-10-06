# Feature Plan: F-M10-4 — Holidays linked to the school-year

**Milestone doc:** `docs/milestones/M10.md` → F-M10-4
**Status:** Plan — not started
**Date:** 2026-09-28
**Depends on:** F-M10-2 (the school's single active school-year) and F-M10-3 (`current_year_q`)

## Overview

Holidays get a `school_academic_year_id` link, so they belong to one school-year the same way term dates do. Existing holidays are backfilled to their school's active school-year. Old holidays are **not archived**: once a school is progressed, the year scope hides them.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend models | Modified | `SchoolHoliday.school_academic_year_id` FK → `SchoolAcademicYear` (null, PROTECT, `db_column="school_academic_year_id"`) |
| Backend services | Modified | `holidays/create.py`: sets the school-year; the overlap check (R-cal-3) is scoped to the current year. `holidays/queries.py::list_holidays`: `current_year_q()` **or** a null school-year (legacy fallback). Edit and delete are unchanged, apart from the overlap scope via the shared create path |
| API / Frontend | None | Same payloads |
| Database migrations | Yes | `AddField` + a `RunPython` backfill (with `schema_editor.connection.alias`, as `check_migration_db_alias.py` requires). Reversible (backfill reverse is a no-op; `RemoveField`) |
| Existing tests | Minor | `tests/holidays/*` fixtures create holidays without a school-year. The legacy null fallback keeps them visible; new create-path tests assert the link |
| Documentation | Update | M4.md note (holidays are now year-linked), M10 Done log |

## Low-Level Design

**Migration `00xx_holiday_school_year`**
1. `AddField` (nullable).
2. `RunPython(backfill)`: for each holiday with a null school-year, set it to the school's single active school-year (via F-M10-2). Holidays of schools with none stay null and are counted in the migration output.

**Services**
- `create_holiday`:
  - `say = get_school_academic_year(school_id)`, which must exist (the session check already implies it). Store it on the row.
  - Overlap query: `SchoolHoliday.objects.filter(school_id, is_active=True, removed=False).filter(current_year_q() | Q(school_academic_year_id__isnull=True))`.
- `list_holidays`: the same filter. **Legacy null rows stay visible** until a school is progressed. F-M10-7 then leaves them null and archived-by-scope, and F-M10-6 warns about them (`LEGACY_NO_SCHOOL_YEAR`).

  After the backfill, dev has 0 null rows (1 holiday total), so the fallback matters only for prod edge cases.

## Business Rules Enforced

- **R-cal-1/2** (a session must exist; dates inside the session window): unchanged. The session is now the school's own (F-M10-3).
- **R-cal-3** (no overlap): only among the current year's holidays.
- **R9:** nothing archived or deleted by this feature.

## Security Review

- No change. Holiday endpoints keep `get_school_or_403` / `can_modify_school`.

## Testing Strategy

**Backend — `tests/holidays/test_f_m10_4_holiday_year.py`**
- **Create:** a new holiday is linked to the school's active school-year.
- **After an archived-year swap** (fixture: archive the school-year and create a new one):
  - old holidays aren't listed
  - a new holiday with the same dates as an old one doesn't conflict (R-cal-3 is scoped)
- **Legacy null rows:** a null-linked holiday is still listed and still checked for overlap.
- **Backfill function:** links existing holidays and leaves those of schools with no school-year null.
- The existing holiday suites stay green.

## Milestones (implementation order)

1. Migration + backfill + tests.
2. Create, list and overlap scoping + tests; full backend suite.

## Open Questions

- None.
