# Feature Plan: F-M10-6 — Precheck and preview (including graduation)

**Milestone doc:** `docs/milestones/M10.md` → F-M10-6
**Status:** Plan — not started
**Date:** 2026-09-28
**Depends on:** F-M10-1 (next class), F-M10-2, F-M10-3, F-M10-5

## Overview

This is the read-only analysis before a run.
- **Precheck** classifies each selected school as `ready`, `warning` or `blocked`, using the blocker and warning codes in M10.md.
- **Preview** computes exactly what execution will create, move and archive, applying the admin's graduation marks.

Both are built on one shared **planner** (`services/progression/planner.py`), which F-M10-7 execution also uses. So the preview can never disagree with the run, and a shared test enforces that.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend models | Modified | `models/child.py::REMOVED_REASONS` gets `("graduated", "Graduated")` (a choices-only migration). `DeactivateIn` is **not** changed |
| Backend services | New | `services/progression/planner.py` (`build_school_plan`), `precheck.py`, `preview.py`, `eligibility.py` |
| Backend API endpoints | New | In `api/admin_progression_api.py`: `GET eligible-schools/`, `POST precheck/`, `POST preview/`, `GET preview/{school_id}/children/`. All admin only |
| Frontend | — | The screens are in F-M10-9. The service functions (`progression.service.ts`) are added here |
| Migrations | Yes | Choices-only `AlterField` on `ChildRemovalLog.removed_reason` |
| Existing tests | None | — |
| Documentation | Update | M10 Done log |

## High-Level Design

```
build_school_plan(school_id, target_year, graduate_class_ids, graduate_child_ids) -> SchoolPlan
   ├─ loads (fixed query count): the school's active school-year; its active SchoolClass, ClassSection,
   │   active children + their active ChildClass/ChildClassSection/BatchChild; SchoolVolunteer;
   │   the counts of Slot / SlotClassSection / SlotClassSectionVolunteer / ClassSectionSubject /
   │   ChildSubject / SchoolSessionDetails to archive; the class catalog (next_class map)
   ├─ blockers[], warnings[]            (codes from M10.md F-M10-6)
   ├─ school_classes: [{class_id, source_school_class_id|None, reason: "copy"|"added_for_promotion"}]
   ├─ sections:       [{source_class_section_id, section_name, section_display_name}]
   ├─ children:       [{child_id, from_class_id, to_class_id|None(graduate), source_ccs_section_id|None}]
   ├─ volunteers:     [source_school_volunteer_id…]
   └─ archive_counts: {table: n}
precheck(...)  = [plan.status/blockers/warnings per school]         (no graduation input)
preview(...)   = [plan counts + class breakdown per school]
execute (F-M10-7) = apply(plan)                                     (same plan object)
```

**The target class for each child** is `graduate` if the child is marked or their class is marked. Otherwise it's `catalog[from_class].next_class_id`, or `from_class` itself when that's null.

**Classes added for promotion:** any target class that isn't among the school's current offerings. For example, 7th → 8th adds 8th when the school doesn't offer it.

## Low-Level Design

**Eligibility (`eligibility.py`)**
- `eligible_schools(target_year) -> [{school_id, name, city, current_year_label, eligible, reason}]`.
- Includes every `converted=True` school, marking ineligible ones with a reason code:
  - `ALREADY_ON_TARGET`
  - `ALREADY_IN_RUN` (frozen)
  - `NO_ACTIVE_SCHOOL_YEAR`
  - `TARGET_NOT_LATER`

**Target year rules (shared with F-M10-7 Start)**
- The target is the **global active year** if at least one converted school isn't on it. Otherwise it's the **only inactive year** whose label start is greater than the active year's label start.
- More than one later inactive year gives 400 "Ambiguous target year".
- Labels follow `YYYY-YYYY` (existing validation), so they're compared by their first year.

**Blockers (per school):**
- `NOT_CONVERTED`
- `ALREADY_ON_TARGET`
- `NO_ACTIVE_SCHOOL_YEAR`, if not exactly 1 (after F-M10-2, only 0 is possible)
- `CHILD_CLASS_CONFLICT`: an active child with 0 or more than 1 active `ChildClass` in the current year
- `CHILD_SECTION_CONFLICT`: more than 1 active `ChildClassSection`
- `NEXT_CLASS_INACTIVE`: `next_class` points to an inactive class
- `ALREADY_IN_RUN`
- `TARGET_NOT_LATER`

**Warnings:**
- `NO_NEXT_CLASS`, with n and the class names
- `CHILD_NO_SECTION`, with n
- `CLASS_CLOSED_TARGET`, with the class names
- `LEGACY_NO_SCHOOL_YEAR`: counts of rows with a null school-year (sections, school-volunteers, holidays)
- `ACTIVE_TIMETABLE`, with n slots, slot-classes and assignments
- `ACTIVE_SESSION`

**Endpoints (admin only, `_require_admin`)**
- `GET /api/admin/progression/eligible-schools/?target_year_id=`
- `POST /api/admin/progression/precheck/`: `{target_year_id, school_ids[]}`, at most 100 ids.
- `POST /api/admin/progression/preview/`: `{target_year_id, schools: [{school_id, graduate_class_ids[], graduate_child_ids[]}]}`.
  - The graduate ids are validated as belonging to the school and its current year. Unknown ids give 400.
- `GET /api/admin/progression/preview/{school_id}/children/?class_id=&search=&page=&page_size=`: active children of the school's current year, for picking individuals to graduate (page size 50).

**Preview response per school:**
- `school_classes` `{copied, added:[names]}`
- `sections_copied`
- `children` `{moving:[{from, to, n}], staying:[{class, n}], graduating:n}`
- `volunteers_carried`
- `archive_counts`
- `warnings`

The same child can't be counted twice (the marks are unioned by `child_id`).

## Business Rules Enforced

- **M10 decisions 5–8, 17, 18:** the table map, the next class from the catalog, and graduation marks only in the preview.
- **R8:** the target year resolution.
- **R9:** read only; precheck and preview write nothing.

## Security Review

| Concern | Handling |
|---|---|
| RBAC | ADMIN_ROLES only on every endpoint (not CXO) |
| Input | Id lists are capped at 100 schools. Graduate ids are checked against the school and current year. The child search is ORM `icontains` |
| Data exposure | The child picker returns only id, name, class and section (no date of birth or contact) |

## Testing Strategy

**Backend — `tests/progression/test_f_m10_6_precheck_preview.py`**
- **Blockers and warnings:** each blocker and each warning is detected when present and absent otherwise (a parametrised fixture per code).
- **Target year:**
  - global active year when some schools are behind
  - the later inactive year otherwise
  - ambiguous → 400
  - not later → `TARGET_NOT_LATER`
- **Preview mapping:**
  - 5→6, 6→7 and 7→8 move; 8 stays.
  - With 9th added and 8→9 set, 8→9 moves and 9th is added.
  - Graduating class 8 plus one 8th child individually gives graduating = the class size (no double count).
- **Read only:** row counts of every table are unchanged after precheck and preview.
- **Query count:** constant per school as children grow (10 vs 200).
- **Shared contract test:** `plan.counts == apply(plan).counts`. It lives in the F-M10-7 test module but depends on this planner.
- **API:** admin 200; CO 403; over 100 ids → 422; unknown graduate id → 400.

## Milestones (implementation order)

1. `REMOVED_REASONS` + planner + eligibility + target-year rules + unit tests.
2. Precheck and preview services + endpoints + API tests; full backend suite.
3. `progression.service.ts` functions for these endpoints (UI in F-M10-9).

## Open Questions

- None.
