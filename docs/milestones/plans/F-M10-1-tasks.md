# F-M10-1 Execution Progress

Plan: `docs/milestones/plans/F-M10-1-plan.md`. Not committing; the human commits manually (M9 is also still uncommitted).
**Status:** Complete 2026-09-28. Migrations 0032/0033 are **not applied to dev yet**; the manual check needs them.

## Milestone 1: Model + migrations + rules
- [x] `Class`: `sequence` (default 0), `next_class_id` (FK self, PROTECT, `db_column`), `open_for_enrolment` (default True); ordering `["sequence", "class_code"]`
- [x] Migrations:
  - `0032_class_catalog_fields` (schema)
  - `0033_seed_class_catalog` (seed 5→6→7→8, 8th closed; reversible; DB-alias safe)
- [x] `services/catalog/rules.py`: `assert_class_open_for_enrolment(cls, allow_prior=)`, `validate_next_class` (self, inactive, cycle)
- [x] `services/catalog/queries.py`: `list_catalog`, `list_open_catalog`
- [x] `services/catalog/write.py`: `create_class`, `update_class`, deactivation guards
- [x] Callers switched: `add_class_to_school`, `enroll`, `edit`, `reactivate` (prior class compared by catalog class). `BLOCKED_NEW_CLASS_CODES` and `assert_class_not_blocked_for_assignment` removed
- [x] `list_classes_for_school` ordered by sequence
- [x] Existing fixtures (`test_f_m2_4_classes`, `test_f_m2_9_children`, `test_f_m6_4_children`) create class 8 with `open_for_enrolment=False`, matching the seed

## Milestone 2: Endpoints
- [x] `api/admin_classes_api.py`: `GET/POST /api/admin/classes/`, `PATCH /api/admin/classes/{id}/` (ADMIN_ROLES only)
- [x] Public `GET /api/classes/` = `list_open_catalog()` (open + active, ordered by sequence)
- [x] Tests `tests/catalog/test_f_m10_1_class_catalog.py` (20):
  - seed and unseed
  - rules: open/closed, allow_prior, self / inactive / cycle, none allowed
  - the enrolment switch is data-driven
  - deactivation guards
  - API: order with "10" after "8", usage count, create 9th and point 8th at it, duplicate 409, cycle 400, toggle, non-admins (CO, CHO, CXO) 403
  - public catalog; school class order
- [x] Full backend suite: 978 passed; `makemigrations --check` clean; migration DB-alias check passed

## Milestone 3: Frontend
- [x] `lib/api/services/catalog.service.ts`
- [x] `app/admin/classes/page.tsx` (admin guard, same as `/admin`)
- [x] `components/admin/ClassCatalogPage.tsx`:
  - table: Order, Class, Code, Next class, Open-for-enrolment switch, In use, Status, Edit
  - loading skeleton and retry
- [x] `components/admin/ClassEditDrawer.tsx`: RHF + Zod shape validation, next-class select (excludes itself, "None — children stay"), enrolment switch, Deactivate/Reactivate, server errors inline
- [x] `AdminPage.tsx`: sidebar "Setup" group with links to Classes and Academic Years
- [x] Vitest (10):
  - `ClassCatalogPage.test.tsx` (7)
  - `AdminSetupLinks.test.tsx` (1)
  - `AdminClassesRoute.test.tsx` (2)
- [x] Full frontend suite: 250 passed; lint and typecheck on touched files clean
- [ ] Manual check: apply migrations to dev, then as an admin add 9th, set 8th → 9th, toggle 8th, and check a school's Add Class dropdown

## Deviations
- **Setup links placement.** They're a **sidebar group** ("Setup") in AdminPage instead of a header row, because AdminPage already has a sidebar with a "Sections" group, so this matches the existing pattern.
- **Program lookup.** `get_foundation_program_id` wasn't moved to `services/catalog/queries.py`. `create_class` imports it from `children/enroll.py`, which avoids a circular import with no behaviour change.
- **Error message.** It keeps the substring "cannot be assigned directly" so the existing assertions still hold. The new text says the class is "closed for new enrolment".
- **Extra.** The drawer also has Deactivate/Reactivate, covering the plan's Status column, and the school class list now orders by sequence.

## Blockers
- None
