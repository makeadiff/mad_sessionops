# Feature Plan: F-M10-5 — Progression run model, row log and school freeze

**Milestone doc:** `docs/milestones/M10.md` → F-M10-5 (and Part 1 decision 5)
**Status:** Plan — not started
**Date:** 2026-09-28
**Depends on:** F-M10-2

## Overview

This adds the three audit models (`ProgressionRun`, `SchoolProgression`, `ProgressionRowLog`) and the **freeze**. A school whose `SchoolProgression` is `queued`, `running` or `failed`:
- rejects every user write with 409 `school_progressing`
- is hidden from COs and CHOs
- is visible read-only to admins

System syncs aren't blocked. A **Release** endpoint unfreezes a failed school on its old year.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend models | New | `models/progression.py` (3 models), registered in `models/__init__.py` |
| Backend services | New + Modified | New `services/progression/freeze.py`. `services/rbac/scope.py`: `schools_visible_to` and `get_school_or_403` hide frozen schools from non-admins. `api/auth_api.py::get_my_permissions` returns `can_modify=False` for frozen schools. `api/schools_api.py::list_schools` adds `progressing_count` |
| Middleware | New | `sessionops/middleware/progression_freeze.py`: any non-safe method (not GET, HEAD or OPTIONS) on `^/api/schools/(\d+)/` for a frozen school returns 409 JSON `{"error": {"code": "school_progressing", ...}}`. Added to `MIDDLEWARE` after auth. Every school write router is mounted under `/api/schools/` (checked in `routes.py`); sync endpoints use other prefixes |
| Backend API endpoints | New | `POST /api/admin/progression/runs/{run_id}/schools/{school_id}/release/` (admin) |
| Frontend | Modified | `SchoolListPage.tsx`: dismissible banner when `progressingCount > 0`. `schools.service.ts` maps the new field. Admin school views already respect `canModify` via `useUserCan` |
| Migrations | Yes | 1 migration creating the 3 tables. Additive |
| Existing tests | Minor | `list_schools` response gets a new field; schema tests may need updating |
| Documentation | Update | BUSINESS_RULES.md: "a school being progressed is frozen", M10 Done log |

## Low-Level Design

### Models (`models/progression.py`)

These are append- and update-only audit rows with no soft-delete columns, like `ExportLog` (R9 exception, noted in BUSINESS_RULES).

```python
RUN_STATUSES = [("in_progress",…), ("completed",…), ("completed_with_failures",…)]
SCHOOL_STATUSES = [("queued",…), ("running",…), ("completed",…), ("failed",…), ("undone",…), ("released",…)]
FROZEN_STATUSES = ("queued", "running", "failed")

class ProgressionRun(models.Model):
    run_id = BigAutoField(pk)
    from_academic_year_id = FK(AcademicYear, PROTECT, db_column=…)   # global year before Start
    to_academic_year_id   = FK(AcademicYear, PROTECT, db_column=…)
    started_by = FK(User, PROTECT, related_name="+")
    status = CharField(choices=RUN_STATUSES, default="in_progress")
    started_at = DateTimeField(auto_now_add); finished_at = DateTimeField(null)
    cleanup = JSONField(default=dict)   # e.g. {"archived_non_converted_say_ids": [...]}

class SchoolProgression(models.Model):
    school_progression_id = BigAutoField(pk)
    run_id = FK(ProgressionRun, PROTECT, db_column="run_id", related_name="schools")
    school_id = BigIntegerField(db_index=True)
    from_school_academic_year_id = FK(SchoolAcademicYear, PROTECT, db_column=…, related_name="+")
    to_school_academic_year_id   = FK(SchoolAcademicYear, PROTECT, null=True, db_column=…, related_name="+")
    status = CharField(choices=SCHOOL_STATUSES, default="queued")
    graduate_class_ids = JSONField(default=list); graduate_child_ids = JSONField(default=list)
    counts = JSONField(default=dict); warnings = JSONField(default=list); error = TextField(null=True)
    started_at / finished_at / undone_at = DateTimeField(null); undone_by = FK(User, null, PROTECT, related_name="+")
    class Meta:
        indexes = [Index(fields=["school_id", "status"])]
        constraints = [UniqueConstraint(fields=["school_id"], condition=Q(status__in=FROZEN_STATUSES),
                                        name="uniq_unfinished_progression_per_school")]

class ProgressionRowLog(models.Model):
    row_log_id = BigAutoField(pk)
    school_progression_id = FK(SchoolProgression, PROTECT, db_column=…, related_name="row_logs")
    table = CharField(max_length=50)            # Django db_table name
    row_id = BigIntegerField(); source_row_id = BigIntegerField(null=True)
    action = CharField(choices=[("created",…), ("archived",…)])
    meta = JSONField(default=dict)   # e.g. {"restore_removed": true} for graduation-retired links (F-M10-8 undo)
    class Meta: indexes = [Index(fields=["school_progression_id", "table"])]
```

Every FK field whose name ends in `_id` sets `db_column` explicitly (`test_model_column_conventions.py`).

### Services (`services/progression/freeze.py`)

- `frozen_school_ids() -> set[int]`: one query on `status__in=FROZEN_STATUSES`.
- `is_school_frozen(school_id) -> bool`.
- `release_school(school_progression, user)`: `failed` → `released`; the run's status is recomputed. A school in any other status gets 409.

### Scope changes (`services/rbac/scope.py`)

- `schools_visible_to(user)`: when the scope isn't admin, `.exclude(partner_id__in=frozen_school_ids())`.
- `get_school_or_403`: a non-admin requesting a frozen school gets `NotFound` (hidden).
- `can_view_school` stays as it is for admins.

### Middleware (`middleware/progression_freeze.py`)

- Matches `request.path` against `^/api/schools/(\d+)/`.
- If the method isn't safe and `is_school_frozen(id)`, returns a `JsonResponse` with status 409 and the error envelope used by `routes.py` handlers.
- It skips any path that doesn't match, so admin, internal and sync routes are never blocked.

### API

- `list_schools`: `progressing_count` = the number of frozen schools in the user's **unfiltered** scope (so the CO banner shows how many are hidden). Admins get 0, because they see those schools.
- `get_my_permissions`: returns `can_modify=False` when the school is frozen.
- **Release endpoint:** in `api/admin_progression_api.py` (created here, and extended in F-M10-6 to 8), admin only.

## Business Rules Enforced

- **New:** a school being progressed is frozen. That means no user writes, it's hidden from COs and CHOs, and admins can only read it.
- **At most one unfinished progression per school**, enforced by a DB constraint.
- **R9:** the audit tables are append and update only.

## Security Review

| Concern | Handling |
|---|---|
| Writes on a frozen school | Blocked centrally by the middleware, for every role including admin. The only path is the progression endpoints (under `/api/admin/progression/`) |
| Visibility | Non-admins get 404 or omission. Admins see the school with a badge |
| Sync | Paths outside `/api/schools/` aren't blocked. The row lock during execute (F-M10-7) covers consistency |
| Release | Admin only |

## Testing Strategy

**Backend — `tests/progression/test_f_m10_5_freeze.py`**
- **Model conventions:** the column-conventions test passes. A second unfinished `SchoolProgression` for the same school gives `IntegrityError`.
- **Freeze on write:** for `queued`, `running` and `failed`, one POST, PATCH and DELETE to each of these write routers returns 409 `school_progressing`: children, classes, buckets, slots, slot-classes, sessions, holidays. GET still works for an admin.
- **Visibility:**
  - A CO's `list_schools` omits the frozen school, and `progressing_count=1`.
  - A CO's school detail gives 404.
  - An admin sees the school, and permissions show `can_modify=false`.
- **Not frozen:** `completed`, `undone` and `released` schools behave normally.
- **Syncs:** a realtime-sync call for a user at a frozen school succeeds.
- **Release:** failed → released unfreezes the school; releasing a `completed` school gives 409.

**Frontend:** the SchoolListPage banner shows the count and can be dismissed.

## Milestones (implementation order)

1. Models + migration + freeze service + tests.
2. Scope, middleware, permissions and `list_schools` field + tests; full backend suite.
3. Release endpoint + frontend banner + tests.

## Open Questions

- None.
