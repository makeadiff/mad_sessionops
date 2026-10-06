# Feature Plan: F-M10-2 — School-year integrity

**Milestone doc:** `docs/milestones/M10.md` → F-M10-2
**Status:** Plan — not started
**Date:** 2026-09-28
**Depends on:** none (can go before or after F-M10-1)

## Overview

This guarantees exactly **one active `SchoolAcademicYear` per school**, with a partial unique DB constraint, and makes every write path resolve the school-year through one helper. It removes two crash paths in enroll and reactivate, which use `.get(...)` and raise `MultipleObjectsReturned` or a 409 when no row exists. It also fixes reactivation across a year boundary, where the child's prior class is compared by catalog class instead of by the old-year `SchoolClass` id.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend models | Modified | `SchoolAcademicYear.Meta.constraints` gains `uniq_active_say_per_school` |
| Backend services | Modified | `services/academic_year/queries.py`: new `get_school_academic_year(school_id)`, and `get_or_create_school_academic_year` uses it. `children/enroll.py` and `children/reactivate.py` use `get_or_create_school_academic_year`. `reactivate.py` places the child in the **current** school-year's `SchoolClass` for the catalog class |
| Backend API endpoints | None | Behaviour change only: enrolling into a school with no school-year now creates one instead of returning 409 |
| Frontend | None | — |
| Database migrations | Yes | 1 migration: a `RunPython` precheck that aborts with the offending school ids, then `AddConstraint`. Reversible (`RemoveConstraint`) |
| Existing tests | Update | Tests asserting "No active academic year binding found" (409) on enroll or reactivate now expect success (a school-year is created) |
| Documentation | Update | BUSINESS_RULES.md: new rule "one active school-year per school" (next to R8) |

## High-Level Design

**Writes:**
```
any write → get_or_create_school_academic_year(school_id, user)
             ├─ get_school_academic_year(school_id)  → the one active row (DB-guaranteed)
             └─ none → create for the global active AcademicYear (unchanged; mid-year joiners)
```

**Reactivate:**
```
payload.school_class_id → must be an active SchoolClass of the school's CURRENT school-year
prior class = catalog class of the child's most recent ChildClass (any year)
closed-class check allowed when target.class_id == prior class_id
```

## Low-Level Design

**Migration `00xx_one_active_school_year`**
1. `RunPython(check_no_duplicates)`, using `schema_editor.connection.alias`:
   - Groups active, non-removed school-years by `school_id`.
   - If any school has more than one, raises `RuntimeError("Schools with >1 active school_academic_year: [...]")`.
   - Dev had 0 on 2026-09-28.
2. `AddConstraint(UniqueConstraint(fields=["school_id"], condition=Q(is_active=True, removed=False), name="uniq_active_say_per_school"))`.

**Services**
- `get_school_academic_year(school_id) -> SchoolAcademicYear | None`: `filter(school_id, is_active=True, removed=False).first()`.
- `get_or_create_school_academic_year`: uses it. The creation path is unchanged. An `IntegrityError` from a concurrent create is caught, and the existing row is re-read.
- **`enroll_child`, step 4:** `say = get_or_create_school_academic_year(school_id, user)`.
  - The school class must belong to that school-year: `school_class.school_academic_year_id == say`.
  - Otherwise 400: "Class is not part of the school's current year". Before F-M10-3, that year-filters the class list, this can only happen for old-year classes.
- **`reactivate_child`:**
  - Resolve `say` the same way.
  - Require `school_class.school_academic_year_id == say`.
  - `is_prior_class = prior_cc and prior_cc.school_class_id.class_id_id == school_class.class_id_id`.

  (This shares the check with F-M10-1's `assert_class_open_for_enrolment(allow_prior=...)`. Whichever feature lands first adds it.)

## Business Rules Enforced

- **R8:** one global active year (unchanged).
- **New:** exactly one active school-year per school, enforced at the DB and relied on by every read in F-M10-3.
- **R9:** no deletes. The migration never "fixes" duplicates; it stops and reports them.

## Security Review

- No new endpoints and no RBAC change. Enroll and reactivate keep `get_school_or_403` / `can_modify_school`.

## Testing Strategy

**Backend — `tests/academic_year/test_f_m10_2_school_year_integrity.py`**
- **The constraint:** inserting a second active school-year for a school raises `IntegrityError`. A second one that's inactive or removed is allowed.
- **The migration precheck:** call `check_no_duplicates` against a DB with a seeded duplicate → `RuntimeError` naming the school.
- **`get_or_create`:**
  - It returns the existing row, even when it's for a non-global year (a school not yet progressed).
  - It creates a row for the global year when there's none.
- **Enroll:**
  - A school without a school-year gets one created and the child is enrolled.
  - A class from an archived school-year gives 400.
- **Reactivate:**
  - A child whose prior `ChildClass` is in an archived year, with a closed prior class (8th), goes into the current year's 8th.
  - A different closed class is still rejected.
- **Existing tests:** update the 409 "no binding" cases.

## Milestones (implementation order)

1. Migration + constraint + tests.
2. Service changes in enroll and reactivate + tests; full backend suite.

## Open Questions

- None.
