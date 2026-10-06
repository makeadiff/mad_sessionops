# Feature Plan: F-M10-3 — Year-scoped reads by the school's own active year

**Milestone doc:** `docs/milestones/M10.md` → F-M10-3
**Status:** Plan approved 2026-09-29 — not started
**Date:** 2026-09-28
**Depends on:** F-M10-2 (one active school-year per school, which makes "the school's active school-year" well defined)

## Overview

Every read of year-bound data (classes, sections and buckets, slots, slot-classes, assignments, term dates, holiday windows, counts, exports) must filter on **the school's own active `SchoolAcademicYear`** instead of the global `AcademicYear.is_active`, and instead of no filter at all.
- **Two helpers:**
  - `current_year_q(prefix)` replaces the M9 `active_year_slot_q` (which used the global year).
  - `get_active_session(school_id)` switches to the school's school-year.
- **Where the filter is missing today:** `list_classes_for_school`, `list_buckets_for_school`, bucket name pre-checks, the R7 overlap check, and the bucket lookups in enroll, edit and bucket membership.

After this feature, a school's old-year rows vanish everywhere as soon as its school-year is archived (F-M10-7), and schools that haven't been progressed keep seeing their own year.

## ⚠ Behaviour change in current data (needs a decision)

A read-only dev profile on 2026-09-28 shows that **16 schools have their only active school-year on 2025-2026** (63 are on 2026-2027). They're effectively schools that Bubble never moved forward.
- **Today:** M9 decision 9 filters on the **global** year, so their 2025-26 slots and assignments are **hidden** (5 slots and 12 assignments in dev).
- **After F-M10-3:** they **reappear** for those 16 schools, because each school's own year is 2025-26. This is exactly M10 decision 10 ("schools not yet progressed keep working in their year").
- **What it means for the first run:** the first real M10 run can progress these 16 schools **into 2026-2027, which is already active, so no flip is needed**. It's a natural first use and a real-data test.

See Open Question 1.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend services | Modified | `services/academic_year/queries.py`: `current_year_q(prefix)` added, `active_year_slot_q` removed, `get_active_session` moved to use the school-year. Callers of `active_year_slot_q`: `slots/create.py` (`list_slots`), `slot_classes/helpers.py` (R6), `slot_classes/schedule.py`, `schools/queries.py` (assignments count), `volunteers/list.py`, `exports/{gaps,schools,timetable,volunteers}.py`. Newly scoped: `structure/queries.py::list_classes_for_school`, `structure/sections.py` (`list_buckets_for_school`, `create_bucket`/`edit_bucket` name pre-checks, the `soft_delete_section` / `soft_delete_school_class` guards), `slots/create.py` + `slots/edit.py` (R7 overlap), `children/enroll.py` / `edit.py` / `structure/bucket_children.py` (bucket lookups), `schools/queries.py::get_school_stats` (classes count), `exports/schools.py` (buckets), `exports/gaps.py` (term dates). |
| Backend models / migrations | None | — |
| API / Frontend | None | Same endpoints and payloads; the rows returned change |
| Existing tests | Update | `tests/exports/test_m9_active_year_filter.py` is rewritten around the school's school-year (its old-year fixture uses a **second inactive** school-year for the school). Suites whose fixtures create slots or classes on an active school-year are unaffected. Any fixture that deliberately creates a second active school-year now violates F-M10-2 and gets fixed |
| Documentation | Update | BUSINESS_RULES.md R6 ("active year" → the school's active year), M9.md decision 9 note, M10 Done log |

## High-Level Design

```python
def current_year_q(prefix: str = "") -> Q:
    """Rows whose school-year is the school's active one (exactly one per school — F-M10-2)."""
    return Q(**{f"{prefix}school_academic_year_id__is_active": True,
                f"{prefix}school_academic_year_id__removed": False})
```

- Works unchanged for single-school and cross-school queries, because each school has exactly one active school-year.
- No extra query (the M9 helper did one lookup per call). So the M9 query-count caps drop back by 1.
- Prefixes by model:
  - `Slot` / `SchoolClass` / `ClassSection` / `SchoolVolunteer` / `BatchChild`: `""`
  - `SlotClassSection`: `"slot_id__"`
  - `SlotClassSectionVolunteer`: `"slot_class_section_id__slot_id__"`
  - `ChildClassSection`: `"class_section_id__"`
  - `ChildClass`: `"school_class_id__"`
  - `SchoolSessionDetails` uses a field without the `_id` suffix: `school_academic_year__is_active`. It gets its own small Q.
- **`get_active_session(school_id)`:** `SchoolSessionDetails.objects.filter(school_id, school_academic_year__is_active=True, school_academic_year__removed=False, is_active=True, removed=False).first()`.
- **Sections with a null school-year** (legacy; 0 in dev) fall outside `current_year_q`. That's accepted: F-M10-6 surfaces them as the `LEGACY_NO_SCHOOL_YEAR` warning, and the Day-1 profile confirms 0 in prod.

**Rule of thumb for review:** after this feature, `AcademicYear.objects.filter(is_active=True)` appears only in:
- `get_active_academic_year`, used for the global label and the 404 guards
- `get_or_create_school_academic_year`, used to create for new schools
- the progression services

A grep check is added to the checklist.

## Low-Level Design (change list)

| File | Change |
|---|---|
| `services/academic_year/queries.py` | + `current_year_q`; − `active_year_slot_q` |
| `services/sessions/queries.py` | `get_active_session` uses the school-year's active flag |
| `services/structure/queries.py` | `list_classes_for_school`: `current_year_q()` |
| `services/structure/sections.py` | `list_buckets_for_school`, `list_sections_for_class`: `current_year_q()`. Name pre-checks in `create_bucket` / `edit_bucket`: `is_active=True, removed=False` **and** `current_year_q()` (so an archived "Group A" never blocks a new one). `soft_delete_*` guards count only current-year dependants |
| `services/structure/bucket_children.py`, `services/children/enroll.py`, `services/children/edit.py` | Bucket / section lookups add `current_year_q()` |
| `services/slots/create.py`, `services/slots/edit.py` | `list_slots` and the R7 overlap queries: `current_year_q()` |
| `services/slot_classes/helpers.py` | R6: `current_year_q("slot_class_section_id__slot_id__")` |
| `services/slot_classes/schedule.py`, `services/volunteers/list.py`, `services/schools/queries.py` | Replace `active_year_slot_q` with `current_year_q`. `get_school_stats`: the classes count gets `current_year_q()` |
| `services/exports/*` | Replace the helper. `schools.py` buckets and term dates, and `gaps.py` term dates, use the school's school-year |

## Business Rules Enforced

- **R1, R2, R6, R7, R-bucket, section and bucket name uniqueness:** evaluated only within the school's active year.
- **M9 decision 9** ("only the active year is visible"): its meaning becomes the school's active year. M9.md gets an annotation.

## Security Review

- Read-scoping only, with no RBAC change. Cross-school exports still use `schools_visible_to`.

## Testing Strategy

**Backend — `tests/academic_year/test_f_m10_3_year_scope.py`**, plus a rewrite of `tests/exports/test_m9_active_year_filter.py`.
- **Fixture:** a school with an **archived** old school-year that holds a class, a bucket, a slot plus slot-class plus assignment, and a session, and an **active** new school-year that holds its own set.
- **Every surface shows only new-year rows:**
  - class list, bucket list, sections for a class
  - slots, schedule
  - volunteers count, R6
  - school stats
  - session and holiday window
  - all 4 exports
- **R7:** an archived slot at the same time doesn't cause an overlap conflict.
- **Name reuse:** "Group A" can be created in the new year while an archived "Group A" exists.
- **Two schools** (one on 2025-26 active, one on 2026-27 active) each see their own data in the same cross-school export.
- **Query-count tests** in the M9 exports return to their pre-M9-decision caps, since there's no year lookup.
- Full backend suite green.

## Milestones (implementation order)

1. Helper + session helper + slots / R6 / R7 / schedule / volunteers (replacing the M9 helper) + tests.
2. Classes, buckets, name checks, bucket lookups and delete guards + tests.
3. Counts and exports + the rewritten M9 filter tests; full backend suite; grep check.

## Resolved Decisions (2026-09-29)

1. **The 16 schools on 2025-26:** accepted as the M10 model. They'll show their own 2025-26 data after this feature, and **the first real M10 run will progress these 16 schools into 2026-27** (no global flip needed). That run doubles as a real-data test.
2. F-M10-2's full backend suite is re-run and confirmed green before this feature starts.

No open questions remain for F-M10-3.
