# Feature Plan: F-M10-1 — Class catalog admin

**Milestone doc:** `docs/milestones/M10.md` → F-M10-1
**Status:** Plan — not started
**Date:** 2026-09-28

## Overview

This makes the class catalog admin-editable data instead of code. `Class` gets three new fields:
- `sequence`: display order
- `next_class_id`: where progression moves children
- `open_for_enrolment`: whether children can be newly enrolled, moved in by editing, or added to a school in that class

The hard-coded `BLOCKED_NEW_CLASS_CODES = {"8"}` is removed; the same behaviour comes from `open_for_enrolment=False` on 8th. A new **Admin → Classes** page lets admins add classes (e.g. 9th) and edit these fields. This feature is the only source progression (F-M10-6/7) uses for "next class".

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Backend models | Modified | `Class` gets `sequence`, `next_class_id`, `open_for_enrolment`; `Meta.ordering` changes to `["sequence", "class_code"]` |
| Backend services | New + Modified | New `services/catalog/` (`queries.py`, `write.py`, `rules.py`). `services/structure/queries.py` drops `BLOCKED_NEW_CLASS_CODES` and `assert_class_not_blocked_for_assignment`; callers in `add_class_to_school`, `children/enroll.py`, `children/edit.py`, `children/reactivate.py` switch to `assert_class_open_for_enrolment` |
| Backend API endpoints | New + Modified | New `api/admin_classes_api.py`: `GET/POST /api/admin/classes/`, `PATCH /api/admin/classes/{class_id}/`. Modified `GET /api/classes/`: list open and active classes ordered by `sequence`, replacing the hard-coded exclusion of "8" |
| Frontend pages | New | `app/admin/classes/page.tsx` |
| Frontend components | New + Modified | New `components/admin/ClassCatalogPage.tsx` and `ClassEditDrawer.tsx`. `AdminPage.tsx` gets a small "Setup" links row: Classes, Academic Years (currently not linked anywhere) and, later, Year Progression |
| Frontend API | New | `lib/api/services/catalog.service.ts` |
| Database migrations | Yes | 1 schema migration (3 fields) plus 1 data migration (seed the current catalog). Both reversible |
| Celery | No | — |
| Existing tests | Update | `test_f_m2_4_classes.py`, `test_f_m2_9_children.py`, `test_f_m6_4_children.py`, `slot_classes/test_create_slot_class.py` expect 8 to be blocked by code. Their fixtures create `Class(class_code="8")` directly, so they must set `open_for_enrolment=False` for class 8. New fields get defaults (`sequence=0`, `open_for_enrolment=True`) so other `get_or_create` fixtures don't break |
| Documentation | Update | BUSINESS_RULES.md (new catalog rules), M10 Done log, tasks file |

## High-Level Design

```
Admin → Classes page ─ GET  /api/admin/classes/            → list_catalog()
                     ─ POST /api/admin/classes/            → create_class()   ─┐
                     ─ PATCH /api/admin/classes/{id}/      → update_class()   ─┴→ validate_next_class(), deactivation guards
CO flows (add class to school / enroll / edit / reactivate) → assert_class_open_for_enrolment(cls, allow_prior=…)
Add-class dropdown ─ GET /api/classes/  (public, unchanged shape) → open + active, ordered by sequence
```

**Key decisions**
- **Enrolment rules live in data, but in one place in code.** `services/catalog/rules.py::assert_class_open_for_enrolment` is the single check. It keeps today's message style: "{class} is closed for new enrolment. Children reach it through year progression."
- **`next_class_id` is FK self with PROTECT**, so a class that's pointed to can't be hard-deleted. The "deactivate" guard also blocks deactivating a class that another class points to.
- **Cycle check** walks the chain from the proposed next class, at most as many steps as there are classes. It's rejected if it reaches the class being edited.
- **Program:** new classes use the single active Program via the existing `get_foundation_program_id()` (in `services/children/enroll.py`), which is moved to `services/catalog/queries.py` and re-exported. Multi-program is out of scope (M10).

## Low-Level Design

### Backend

**Model (`models/grade_class.py`)**

```python
sequence = models.IntegerField(default=0, db_index=True)
next_class_id = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True,
                                  db_column="next_class_id", related_name="previous_classes")
open_for_enrolment = models.BooleanField(default=True)
class Meta: ordering = ["sequence", "class_code"]
```

**Migrations**
1. `00xx_class_catalog_fields`: `AddField` × 3.
2. `00xx_seed_class_catalog`: a `RunPython` (using `schema_editor.connection.alias`) that sets:
   - `sequence = int(class_code)` when numeric, otherwise 1000
   - `next_class` for 5→6, 6→7 and 7→8 when both classes exist
   - `open_for_enrolment=False` for "8"

   The reverse function clears the three fields.

**Schemas (`schemas/catalog.py`)**
- `AdminClassOut`: class_id, class_code, class_name, sequence, next_class_id, next_class_name, open_for_enrolment, is_active, in_use_count.
- `AdminClassCreateIn`:
  - `class_code`: 1–4 characters, stripped
  - `class_name`: 1–20 characters
  - `sequence`: ≥ 1
  - `next_class_id`: optional
  - `open_for_enrolment` defaults to True
- `AdminClassPatchIn`: every field optional, plus `is_active`.

**Services (`services/catalog/`)**
- `queries.list_catalog(include_inactive=True)`: annotates `in_use_count`, the number of active `SchoolClass` rows.
- `write.create_class(payload, user)`:
  - `class_code` must be unique (409 otherwise).
  - `next_class` is checked with `validate_next_class`.
- `write.update_class(class_id, payload, user)`:
  - If `next_class_id` is being changed, run `validate_next_class`.
  - If `is_active=False` is being set, reject with 409 when `in_use_count > 0` or another active class points to this one.
- `rules.validate_next_class(cls, next_cls)`:
  - It can't be the class itself.
  - It must be active.
  - It can't create a cycle.
  - Violations raise 400 `ValidationError`.
- `rules.assert_class_open_for_enrolment(cls, *, allow_prior=False)`:
  - No-op if `cls.open_for_enrolment` or `allow_prior`.
  - Otherwise raises 400.

**Callers**
- `structure/queries.add_class_to_school`: `assert_class_open_for_enrolment(cls)`.
- `children/enroll.py`: `assert_class_open_for_enrolment(school_class.class_id)`.
- `children/edit.py` (class change): `assert_class_open_for_enrolment(new_school_class.class_id)`.
- `children/reactivate.py`:
  - `assert_class_open_for_enrolment(school_class.class_id, allow_prior=is_prior_class)`.
  - `is_prior_class` compares **catalog `class_id`** (the prior `ChildClass.school_class_id.class_id`) with the target's `class_id`. This also fixes the F-M10-2 cross-year case.

**API**
- `api/admin_classes_api.py`: `admin_classes_router`, mounted in `routes.py` at `/api/admin/classes/`. Every handler calls `_require_admin(request.auth)` (`user_has_admin_access`, ADMIN_ROLES only).
- `api/structure_api.py::list_class_catalog`: `Class.objects.filter(is_active=True, removed=False, open_for_enrolment=True).order_by("sequence", "class_code")`.
  - It stays `auth=None`, as it is today.
  - The import of `BLOCKED_NEW_CLASS_CODES` is removed.

### Frontend

- **`lib/api/services/catalog.service.ts`**: `fetchAdminClasses()`, `createClass(input)`, `updateClass(id, patch)`, with snake_case → camelCase mapping like the other services.
- **`app/admin/classes/page.tsx`** (client) → `ClassCatalogPage`. The admin guard is the same as `app/admin/page.tsx`: exact `ADMIN_ROLES` split, otherwise redirect to `/schools`.
- **`ClassCatalogPage.tsx`**:
  - An MUI `Table`: Order · Class · Code · Next class · Open for enrolment (a `Switch` that PATCHes immediately with a toast) · In use · Status · Edit.
  - "Add class" and "Edit" open `ClassEditDrawer`.
- **`ClassEditDrawer.tsx`**:
  - React Hook Form + Zod: code 1–4 characters, name 1–20, sequence integer ≥ 1.
  - Next class is a `Select` of active classes except the one being edited, plus "None — children stay in this class".
  - Backend 400/409 errors are shown inline.
- **`AdminPage.tsx`**: a compact "Setup" link row under the header: **Classes · Academic Years**. **Year Progression** is added in F-M10-9. This gives Academic Years its first nav entry.
- MUI subpath imports and theme tokens throughout.

## Business Rules Enforced

- **Catalog rules (new, recorded in BUSINESS_RULES.md as an R-catalog rule):**
  - next class is active and not the class itself, with no cycles
  - a closed class can't be enrolled into, edited into, or added to a school, except when restoring a child to their prior class
  - a class can't be deactivated while in use or while it's another class's next class
- **R9:** deactivation is `is_active=False`, never a delete. `next_class_id` uses PROTECT.

## Security Review

| Concern | Handling |
|---|---|
| Auth | JWT on the admin endpoints. `GET /api/classes/` stays public, as today; it exposes only names and codes |
| RBAC | `_require_admin`: ADMIN_ROLES only (not CXO). COs and CHOs get 403 |
| Input validation | Pydantic lengths; unique code; integer sequence; `next_class_id` must exist and be active |
| Data exposure | None (catalog metadata) |

## Testing Strategy

**Backend — `tests/catalog/test_f_m10_1_class_catalog.py`**
- **Migration seed:** a data-migration test through the service (fixture replicates it): 5→6→7→8, 8 closed.
- **Create:** a 9th class; a duplicate code gives 409; a CO gets 403.
- **Next class:**
  - Setting 8→9 works.
  - Pointing to itself, pointing to an inactive class, and creating a cycle (7→5 when 5→6→7) each return 400.
- **Deactivation:** blocked while in use (409) and while pointed to by another class (409); otherwise it works.
- **Enrolment switch:**
  - A closed class blocks `add_class_to_school`, enroll and edit-class (400).
  - Reactivating into the prior class is allowed when closed.
  - Opening 8th makes it assignable.
- **Public catalog:** `GET /api/classes/` excludes closed and inactive classes and is ordered by sequence ("10" after "9").
- **Existing suites:** update the four fixtures to set `open_for_enrolment=False` for class 8. Their assertions (blocked messages) otherwise stay the same, apart from the message wording, which is updated in the tests.

**Frontend — `__tests__/admin/ClassCatalogPage.test.tsx`**
- The table renders rows ordered by sequence.
- The switch PATCHes and shows an error toast when the call fails.
- The drawer:
  - validation errors
  - the next-class options exclude the class itself
  - a backend 400 message is shown inline
- Non-admins are redirected.

**Manual:** as an admin, add 9th, set 8th → 9th, toggle 8th open and closed, and check the Add Class dropdown on a school.

## Milestones (implementation order)

1. **Model + migrations + rules service** + backend tests. Existing suites are fixed for the new check. The hard-coded list is removed.
2. **Admin endpoints + public catalog change** + API tests; full backend suite.
3. **Frontend:** the Classes page, the drawer and the Setup link row + Vitest; full frontend suite; manual check.

## Open Questions

- None. The decisions come from M10 (admin-only; next class set explicitly; enrolment toggle).
