# Feature Plan: F-M10-8 — Per-school undo

**Milestone doc:** `docs/milestones/M10.md` → F-M10-8
**Status:** Plan — not started
**Date:** 2026-09-28
**Depends on:** F-M10-7

## Overview

This reverses a `completed` school progression using its `ProgressionRowLog`, but only until anyone writes new-year data for that school. After an undo, the school is on its old year and can be progressed again. The global year is never flipped back.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend services | New | `services/progression/undo.py`: `can_undo(sp) -> (bool, reason)` and `undo_school(sp, user)` |
| Backend API endpoints | New | `POST /api/admin/progression/runs/{run_id}/schools/{school_id}/undo/`. The run detail response gains `can_undo` and `undo_block_reason` per school |
| Models / migrations | None | — |
| Frontend | — | The Undo button is in F-M10-9 |
| Documentation | Update | M10 Done log |

## Low-Level Design

**`can_undo(sp)`** is True only if **all** of these hold:
1. `sp.status == "completed"`.
2. There are **no new-year writes.** For every year-bound table (`SchoolClass`, `ClassSection`, `Slot`, `SchoolVolunteer`, `BatchChild`, `SchoolSessionDetails`, `SchoolHoliday`), the ids of rows with `school_academic_year_id = sp.to_school_academic_year_id` are a subset of the logged `created` ids.
3. No `ChildClass` or `ChildClassSection` rows point to the new year's classes or sections other than the logged ones.
4. No `Child` row was created for the school after `sp.finished_at`.
5. No logged row (created or archived) has `updated_at > sp.finished_at`.

The first failing check gives the reason, for example "A slot was created in 2027-28 after progression".

**`undo_school(sp, user)`** runs in one transaction:
1. Lock the new school-year.
2. Re-check `can_undo`. If it fails, 409 `undo_not_allowed` with the reason.
3. Every **created** row gets `removed=True, is_active=False, deleted_at=now`. They're mistakes, so they're soft-deleted rather than archived.
4. Every **archived** row goes back to `is_active=True`.
5. The new school-year becomes `removed=True`, and the old one `is_active=True`.
6. **Graduated children:** `Child.is_active=True`, with their links restored through step 4 (they were retired with `removed=True`, so they're flagged for explicit restore in the log). The `graduated` removal log is retired, following the `reactivate_child` pattern.
7. `sp.status="undone"`, plus `undone_at` and `undone_by`. Recompute the run status.

**Graduation retire detail:** because `retire_child` sets `removed=True` on links (for deactivate parity), F-M10-7 logs those rows with `action="archived"` and a flag `restore_removed=True`. Undo then clears `removed` as well as setting `is_active`. The field is `ProgressionRowLog.meta` (JSON), defined in the F-M10-5 plan.

## Business Rules Enforced

- **Undo allowed until the first new-year write** (M10 decision 14).
- **One active school-year per school:** the swap happens inside one transaction.
- **R9:** soft operations only.
- **R8:** the global year stays unchanged.

## Security Review

- ADMIN_ROLES only. Undo takes a lock and re-checks eligibility at execution time, so no race can undo past a new write.

## Testing Strategy

**Backend — `tests/progression/test_f_m10_8_undo.py`**
- **Snapshot:** execute then undo, and every table equals the pre-execute snapshot (ignoring timestamps and audit fields). This includes graduated children, their links and the removal log.
- **Blocking writes:** after a new-year slot, bucket, enrolment, session or holiday is written, or after a logged row is edited, `can_undo` is false and names the reason, and the endpoint returns 409.
- **Re-run:** an undone school can be progressed in a new run and ends in the same state as the first execute.
- **Global year:** undo after the flip leaves the global year on the target.
- **Status guards:** a CO gets 403; undoing an `undone` or `failed` school gives 409.

## Milestones (implementation order)

1. `can_undo` + tests.
2. `undo_school` + endpoint + snapshot tests; full backend suite.

## Open Questions

- None. The `ProgressionRowLog.meta` field is already in the F-M10-5 plan.
