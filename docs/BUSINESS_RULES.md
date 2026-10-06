# Business Rules

Every rule in this file is non-negotiable. Each one has business rationale. If you think a rule is wrong, raise it with the human before writing code that violates it — don't work around it.

Rules are enforced at the **service layer** (Python), not at the DB layer, unless noted. This is deliberate: DB constraints can't encode "active" or "soft-deleted" cleanly, and application-layer enforcement gives us better error messages.

## Capacity and composition

### R1 — Maximum 5 children per section

**Rule:** A section may have at most 5 active children at any time. Soft-deleted children don't count toward the limit.

**Rationale:** MAD's pedagogy requires small-group instruction. 5 is the researched cap for volunteer-led sessions.

**Enforcement:** Service layer, before `Child.is_active=True` is set on create or reactivate. Raise `ConflictError` with a specific message.

**DB-level:** Not enforceable cleanly (partial index on `is_active` would work but creates migration friction we don't want).

---

### R2 — Slot-class must have 1 to 5 volunteers, bounded by the bucket's active children (superseded by M6)

**Rule:** When scheduling volunteers to teach a mentoring circle (bucket) in a slot, at least 1 volunteer must be assigned, at most 5 — and volunteer count can never exceed the bucket's current active-children count.

**Rationale:** Solo volunteers burn out; too many volunteers for too few children is inefficient and dilutes instruction quality. The 5-cap and the "class-agnostic bucket" model replaced the original 2-volunteer, class-scoped section design in M6 (`docs/milestones/M6.md`) — this file's original text (`Vol1`/`Vol2`, 1-2 volunteers) described the pre-M6 model and is kept below for historical reference, but is no longer accurate.

**Enforcement:** Service layer, on slot-class create/edit (`check_r_bucket_capacity`, `sessionops/services/slot_classes/helpers.py`) — see R-bucket below for the companion rule on the *removal* side.

<details><summary>Original (pre-M6) text, historical only</summary>

At most 2 may be assigned; `Vol1` is required, `Vol2` is optional.

</details>

---

### R-bucket — Removing/moving a child out of a bucket must not leave a slot-class over-volunteered

**Rule:** A child cannot be removed from a bucket, deactivated, or moved to a different bucket if doing so would leave any of that bucket's scheduled slot-classes with more volunteers than remaining active children (violating R2's capacity bound in reverse).

**Rationale:** R2 only guards the assign-volunteers direction. Without this rule, removing children is a silent backdoor to the same invalid state R2 exists to prevent.

**Enforcement:** Service layer, `assert_bucket_not_over_volunteered()` (`sessionops/services/structure/bucket_children.py`), called with the bucket row locked (`select_for_update()`) from all three places a child can leave a bucket: `remove_child_from_bucket`, `deactivate_child`, and `edit_child`'s bucket-reassignment path. Raises `ConflictError` (409) — the CO must remove a volunteer from the slot-class first; there is no auto-remediation.

---

### R3 — Vol1 must not equal Vol2 (superseded by M6 — see R-bucket's 1-5 volunteer model)

**Rule:** In a slot-class, the same volunteer cannot be assigned as both primary and secondary.

**Rationale:** Obvious. A person isn't two people.

**Enforcement:** Schema-level (Pydantic validator) + service layer. Superseded by the M6 volunteer-list model, where uniqueness across the whole `volunteer_ids` list is validated instead of a Vol1/Vol2 pair specifically.

## Volunteer assignment

### R4 — One volunteer belongs to exactly one school

**Rule:** A volunteer may have active assignments at only one school at any time.

**Rationale:** Volunteers commit per-school. MAD doesn't support cross-school volunteering due to scheduling and accountability.

**Enforcement:** Service layer on `SchoolVolunteer` create. Query: is there any other `SchoolVolunteer` where `volunteer_id=X AND is_active=True`? If yes, raise `ConflictError`.

**Edge case:** A volunteer moving between schools requires the old assignment to be deactivated first. The service exposes a `transfer_volunteer` flow that does both in a single transaction.

---

### R5 — Same section cannot appear twice in the same slot

**Rule:** Within one slot, each section can be scheduled at most once.

**Rationale:** A section is one group of children in one place. They can only be taught one thing at a time.

**Enforcement:** Service layer on slot-class create. Unique-together at the DB level is acceptable here as a belt-and-suspenders check, but soft-delete makes it awkward — primary enforcement is Python.

---

### R6 — Same volunteer cannot have more than one active slot-class assignment

**Rule:** A volunteer can be assigned to at most one slot-class at any time — system-wide, not just within the same slot.

**Rationale:** A volunteer teaches one section at a time. Combined with R4 (one school per volunteer), MAD's volunteering model is one committed weekly teaching slot per volunteer.

**Revised 2026-08-21:** originally scoped to "not two sections in the same slot" only. Broadened after discovering the narrower scope let a volunteer be scheduled into two different (non-overlapping, per R7) slots at the same school — allowed by the old rule's wording, but not an intended real-world commitment pattern.

**Revised 2026-09-28 (M9):** only assignments on slots in the **active academic year** count. The Slots tab, the Volunteers tab, the school list counts and the M9 exports now show only active-year slots and assignments. A leftover old-year assignment (there were 12 in dev at the time) was invisible to ops but still blocked the volunteer from being assigned; this revision removes that trap. The shared filter is `services/academic_year/queries.py::current_year_q`. **Revised again 2026-09-29 (M10 F-M10-3):** "active year" means the **school's own active school-year** (R8a), not the global flag. A school not yet progressed keeps its own year's assignments.

**Enforcement:** Service layer on slot-class create/edit (`check_r6_volunteer_single_assignment` in `services/slot_classes/helpers.py`). Query: does the volunteer have any other active `SlotClassSectionVolunteer` row on an active slot-class whose slot is in its school's active school-year (any slot, any school)? If yes, raise `ConflictError`.

### R-catalog — The class catalog is admin-managed data (M10, 2026-09-28)

**Rule:** Admins (ADMIN_ROLES only) manage the class catalog in Admin → Classes. Each class has:
- an **order** (`sequence`), used to list classes numerically
- an optional **next class** (`next_class_id`), which is where year progression moves its children. No next class means children stay in the same class.
- an **open for enrolment** flag

**Constraints:**
- A next class must be a different, active class, and next-class chains can't form a cycle.
- A class **closed for enrolment** can't be added to a school, enrolled into, or moved into by editing. Only year progression, or reactivation into the child's prior class, can place a child there. This replaces the hard-coded `BLOCKED_NEW_CLASS_CODES = {"8"}`; 8th is seeded as closed.
- A class can't be deactivated while any active school class uses it, or while another class points to it as its next class.

**Enforcement:** `services/catalog/rules.py` (`assert_class_open_for_enrolment`, `validate_next_class`) and `services/catalog/write.py`.

## Scheduling integrity

### R7 — No overlapping slots for the same school on the same day

**Rule:** Two slots at the same school on the same date must not have overlapping time ranges.

**Rationale:** MAD's school partnerships allocate specific time windows. Overlaps mean double-booking resources or staff.

**Enforcement:** Service layer on slot create and update. Query all active slots for `(school, date)` and check for interval overlap.

## Academic year

### R8 — Exactly one academic year is globally active

**Rule:** At all times, exactly one `AcademicYear` row has `is_active=True`. It is the newest year any school has been progressed into, and the year new schools join. Each school works in its own school-year (R8a), so schools can be on different years.

**Rationale:** MAD runs a unified academic calendar. Per-school years were considered and rejected — too much divergence, too complex for reporting.

**Enforcement:** Service layer on year progression transitions (`services/progression/start.py`). Start makes the newest target year active when it is later than the active one; the flip is atomic (old year deactivated + new year activated in one transaction). There is no manual activate/deactivate, and Undo never flips the year back.

**Progression rules (2026-10-05):**
- Each school moves **one year ahead of its own year** (2025-26 → 2026-27, 2026-27 → 2027-28). Unselected schools stay where they are and never block anyone.
- **One school per run** (2026-10-06): every move is chosen, previewed and confirmed on its own (the admin types the school's name to start).
- No skipping: a school two years behind is progressed twice. Its preview warns `STILL_BEHIND`.
- The next year must already exist; otherwise the school is blocked with `NO_NEXT_YEAR`.
- Only the year right after the latest existing year can be created, and only an inactive year that no school or run uses can be removed.

**Denormalization:** `School_academic_year` table only single row should be active

### R8a — Exactly one active school-year per school (M10, 2026-09-28)

**Rule:** Each school has exactly one `SchoolAcademicYear` row with `is_active=True, removed=False`. A school's year-bound data (classes, sections, slots, school volunteers, term dates, holidays) belongs to that row. A school that hasn't been progressed keeps working in its own year even after the global year flips. New schools get a school-year for the global active year on their first write.

**Enforcement:**
- DB: partial unique constraint `uniq_active_say_per_school` (migration 0034, which refuses to apply if duplicates exist).
- Service layer: every write resolves the school-year through `get_or_create_school_academic_year`. Enrol and reactivate accept only classes that belong to the school's current school-year.

## Soft delete

### R9 — No hard deletes anywhere — enforced at two layers (Layer 3 deferred)

**Rule:** model in the domain layer ever has a colymn removed. Deactivation is via `removed=true` and `is_active = false`, recorded with `deleted_at` and (when known) `deleted_by`.


**Enforcement is layered. Two layers are active in v1; a third layer is deferred for future.**

**Layer 1 — Application code (active):**
- Every domain model inherits from `SoftDeleteBaseModel` (or implements its pattern directly, as User does).
- `delete()` sets `is_active=False` amd `removed=true`   , records audit fields, never issues SQL DELETE.
- `hard_delete()` always raises `NotImplementedError`. Anyone who actually wanted a hard delete cannot get one accidentally.
- Custom managers filter `is_active=True` and `removed=false` by default. Use `.all_with_deleted()` to see soft-deleted rows.

**Layer 2 — Foreign key cascades blocked (active):**
- Every FK uses `on_delete=models.PROTECT`.
- This means: even if Layer 1 were bypassed, deleting a parent row would fail because of dependent children.
- PROTECT is the explicit "this hard-delete is not allowed" signal in the schema.


**Risk acknowledged by deferring Layer 3:** A queryset `delete()` call (e.g., `Model.objects.filter(...).delete()`) bypasses the model's `delete()` override and issues SQL DELETE. With Layer 3, this would fail at the DB. Without Layer 3, it succeeds and silently removes rows. Mitigations:
- Code review checks for `.delete()` calls on querysets
- The `SoftDeleteBaseModel.delete()` override on individual instances catches most usage
- Layer 2 (PROTECT) blocks cascades, so a single bad delete won't propagate

**Exceptions to no-hard-delete (deliberate, infrastructure-level):**
- `RefreshTokenBlacklist` (from `simplejwt`) — internal token management, hard-delete is fine
- Celery result rows, cache entries — infrastructure
- `EmailRateLimit` rows — insert-only audit; no deletion mechanism in v1, may add periodic pruning later
- `ExportLog` rows (M9) — append-only export audit; no soft-delete columns because rows are never modified or removed; no retention policy yet (see D031)


**Note on PasswordResetToken:** Despite being short-lived data, password reset tokens follow the no-hard-delete rule via the **one-row-per-user UPDATE-in-place** pattern. A user has exactly one PasswordResetToken row that is overwritten on each new reset request. The row stays for audit; the token within is consumed or rotated.

**What "deletion" means for users in practice:**
- "Delete a child" → `child.is_active=False`, record `deleted_at`, `deleted_by`, mandatory `removed_reason` (R10)
- "Remove a volunteer from school" → soft-delete the SchoolVolunteer row `is_acive=false and removed=true`; the Volunteer record remains
- "Deactivate a user" (HR offboarding) → `user.is_active=False` (typically via Hasura sync)

**If hard-delete is ever genuinely needed:** explicit migration, reviewed, run manually. Never a runtime code path.

### R10 — Removal reason is mandatory when deactivating a child

**Rule:** Setting `Child.is_active=False` requires `removed_reason` to be set in the same operation. It cannot be null, empty, or whitespace-only.

**Rationale:** Attrition analysis. MAD tracks why children leave (moved, illness, dropout, graduated, etc.) for program improvement.

**Enforcement:** Service layer method `deactivate_child(child_id, reason, user)`. No direct model access should bypass this.

**Note:** Other models (volunteers, slots, sections) may have optional removal reasons — only `Child` has it as mandatory.

## Authentication and access

### R11 — Academic Support and Fellow roles have no Session-Ops login

**Rule:** Users with `role='academic_support'` or `role='fellow'` exist in the User model (they sync from Hasura) but cannot authenticate to Session-Ops.

**Rationale:** Session-Ops is an operational tool for COs, CHOs, and admins. Academic support and fellows consume outputs elsewhere.

**Enforcement:** Auth service rejects login attempts from these roles with a generic "authentication failed" response. Do NOT distinguish "role not allowed" from "bad credentials" — that leaks role information.

---

### R12 — Deactivated users cannot authenticate

**Rule:** Users with `is_active=False` cannot log in or refresh tokens. Existing tokens they hold are rejected.

**Rationale:** When a user leaves MAD, immediate access revocation without having to delete the user row.

**Enforcement:** JWT middleware filters `is_active=True` in the User lookup. Deactivation doesn't invalidate existing tokens instantly (JWTs are stateless), but tokens fail validation on next request because the lookup returns nothing.

**Response:** Generic 401, same as any other auth failure. Do not leak "account disabled."

## Data integrity

### R13 — Scope filtering is default, bypass is explicit

**Rule:** Every queryset in service code defaults to filtering by the caller's RBAC scope. Admins bypassing scope must do so via an explicit method (`all_schools()`, `all_users()`), never by accident.

**Rationale:** Easier to audit explicit bypasses than to hunt for missing filters.

**Enforcement:** Service query helpers. Reviewers check that no view calls a raw `.objects.all()` on a scope-sensitive model.

---


## Operational

### R16 — Hasura sync events are idempotent

**Rule:** Replaying a Hasura webhook event must produce the same state as processing it once.

**Rationale:** Hasura retries failed webhooks. Non-idempotent handlers cause duplicates and bad data.

**Enforcement:** Sync tasks use upsert patterns keyed on Hasura IDs, not blind inserts. Tests verify replay.

---

### R17 — A converted school that becomes non-converted in the CRM (removed or not) has its full operational footprint cascade-deactivated

**Rule:** During partner sync, if a Hasura partner row reports `converted=false` (whether or not `crm_partner_removed` is also true — the dbt model sets `converted=false` whenever a school is removed; extended 2026-10-01) while the partner was previously `is_active=true` **and previously `converted=true`** in Session-Ops, the entire school is treated as dropped from the CRM's active pipeline: every active row across `slot_class_section_volunteer`, `slot_class_section`, `slot`, `class_section_subject`, `school_volunteer`, `child_class_section`, `batch_child`, `child_program`, `child_subject`, `child` (with a `ChildRemovalLog` per child), `child_class`, `class_section`, `school_class`, `school_academic_year`, `school_session_details`, and `school_holiday` is soft-deactivated, and `Partner.is_active` is forced to `false`.

**Rationale:** This condition is independent of, and takes priority over, F-M1-2's existing `crm_partner_removed`-only flag flip (`Partner.is_active = not crm_partner_removed`) — under that logic alone, `removed=false` would leave (or make) the partner active. Without R17, a school that the CRM no longer counts as converted — but that was never formally marked "removed" — leaves fully-staffed, fully-scheduled ghost data in Session-Ops indefinitely.

**The previous-`converted=true` requirement is load-bearing, not incidental.** An earlier version of this rule fired on "previously active" alone, without checking previous `converted` status. That broke a real production case: a partner that has *never* been converted (a plain lead) is still created with `is_active=true` on its very first sync — `is_active` is driven only by `crm_partner_removed`, unrelated to `converted`. Checking only "previously active" meant every never-converted lead matched "removed=false, converted=false" again on its *second* sync (nothing had changed), and got wrongly cascade-deactivated — and would keep re-matching on every sync after that. Requiring the partner to have previously been `converted=true` restricts R17 to an actual converted→reverted transition, never a lead that was never converted in the first place.

**Enforcement:** Service layer, `services/sync/partner_deactivation.py::cascade_deactivate_school`, called from the single shared upsert path `services/sync/upsert.py::bulk_upsert_partners` (used by both the cron incremental sync and the manual "Sync now" trigger — see F-M4-9). Both the "previously active" and "previously converted" checks are snapshotted before the upsert overwrites those fields, so a brand-new partner seen for the first time never triggers this (nothing to deactivate yet, and never previously converted), and an already-cascaded partner is a no-op on repeat syncs (every cascade query filters `is_active=true`). The partner upsert and its cascades commit in **one transaction** (2026-10-01): if a cascade fails, the partner rows roll back too, so the next sync still sees the partner as previously converted and retries the cascade instead of losing it.

**Note:** Every write is `is_active=false` + `removed=true` (or `is_active=false` alone for `Partner`, which has no `removed` field) + `deleted_at` — no hard deletes, consistent with R9. `ChildRemovalLog.removed_reason` is always written as `"other"` with `other_details="School dropped from CRM"`, satisfying R10's mandatory-reason requirement in an automated context with no human operator to ask. There is no automatic reactivation: if the partner's CRM state later reverts to `converted=true`, cascaded child records stay deactivated — confirmed as permanently out of scope, not just deferred.

---
---

## Conventions, not rules

These are strong defaults but not quite as load-bearing. Violate only with reason.

- All timestamps are stored in UTC. Display conversion happens on the frontend.
- All money fields (if any appear later) are integer paise/cents, not float rupees/dollars.
- All enum values are lowercase snake_case strings stored as CharField with choices, not Django enum types (simpler migrations).
- Serializer field names match model field names exactly unless there's a specific reason to rename.
