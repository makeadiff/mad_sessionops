# Session-Ops Milestones

The plan for getting Session-Ops into production. Five milestones, ~2 weeks each, each ending in a real production deploy.

This is the central overview. Per-milestone deep specs live under `docs/milestones/MX.md` and are written **at the start of each milestone**, not all upfront.

---

## How milestones work

A milestone is **not** a sprint. A sprint is a time box. A milestone is a shippable, deployed product release.

Each milestone:

- Is ~2 weeks of calendar time
- Reserves the last 3-4 days for **stabilization** — testing, bug fixes, production deploy, smoke testing in production
- Ends with users actually using what was built
- Builds on the previous milestone — does not redo work

**The principles:**

1. **Build basic CRUD first.** Don't block users from collecting data. Polish features (checklists, UX guidance) come later, once the data model works.
2. **Easy first, complex later.** Things with fewer architectural decisions ship earlier. Things with cross-cutting concerns (year progression, Google OAuth, real-time webhook sync replacement) come later.
3. **A milestone is the smallest useful product release.** Don't add scope in the middle. If a need surfaces, address it next milestone.

---

## Definition of "production ready"

For every milestone, "done" means all of:

- Code merged to main on both repos
- Migrations applied in production DB
- Backend deployed on production EC2
- Frontend deployed
- Smoke test passed in production: a real user can complete the milestone's primary user flow
- Sentry error rate is at baseline (no new error spikes in 24h post-deploy)
- Rollback plan documented (how to revert if something breaks)

If any of those fail, the milestone is not done. Don't move to the next milestone with the previous one half-shipped.

---

## Timeline overview

| # | Milestone | Theme | Features | Status | Detailed doc |
|---|---|---|---|---|---|
| M1 | Auth + School Visibility | Password login, RBAC, Hasura sync, school list + detail | 5 | Complete | `docs/milestones/M1.md` |
| M2 | School Structure + Children | Academic year, classes, sections, children CRUD | 9 | In progress — backend + frontend complete; production deploy pending | `docs/milestones/M2.md` |
| M3 | Volunteers + Scheduling | Volunteer assignments, slots, slot-classes, schedule validation | 10 | Not started | Written at M3 start |
| M4 | Calendar + Ops + Webhook Sync | Session dates, holidays, deactivation alerts, Hasura webhooks | 6 | Not started | Written at M4 start |
| M5 | Activation, Polish, Admin Ops | Google OAuth, sync admin dashboard, setup checklist, cross-school conflict, Celery+Redis (year progression moved to M10) | 10 | Not started | Written at M5 start |
| M9 | CSV Data Export for Ops | Per-school rosters and timetable, schools summary, cross-school children/volunteers, ops gap report, export audit log | 8 | Features complete and verified (2026-09-28); commit and deploy pending | `docs/milestones/M9.md` |
| M10 | Year Progression | Admin class catalog (next class, enrolment toggle), one active year per school, reads scoped to the school's year, holiday year link, precheck/preview/run/undo wizard | 9 | Features complete (2026-09-30); commit, migrations and prod-copy dry run pending | `docs/milestones/M10.md` |

**Total expected duration:** 10 weeks of build + stabilization. Each milestone's start date is "when the previous milestone ships," not a fixed calendar date. M5 may run slightly longer (2-2.5 weeks) given its size; build at the pace M1-M4 actually takes.

---

# Milestone 1 — Auth + School Visibility

**Status:** In progress
**Production goal:** A user signs in with email + password, sees the schools they have access to, and can view a school's basic details.

## Features

- **F-M1-1** Password authentication — set, login, forgot password (Brevo email)
- **F-M1-2** Hasura scheduled sync — system cron every 6 hours, fetches users + partners
- **F-M1-3** RBAC scope filtering — CO sees own schools, admin sees all, CHO empty list
- **F-M1-4** School list page — scope-filtered, with search
- **F-M1-5** School detail page — Overview tab only; other tabs disabled placeholders

## Major in-scope items

- Password auth (set, login, forgot)
- Hasura sync (users + partners, cron-driven, no Celery)
- School list and detail (read-only)
- RBAC scope service
- Production deploy at https://sessionops.makeadiff.in

## Major out-of-scope items

- Google OAuth (M5)
- School configuration (M2)
- Children, volunteers, slots (M2-M3)
- Real-time webhook sync (M4)
- Sync admin UI (M5)

> **Detailed M1 spec:** `docs/milestones/M1.md`

---

# Milestone 2 — School Structure + Children

**Status:** In progress — backend + frontend complete (2026-05-07); production deploy pending
**Production goal:** A CO can build out a school's class structure (academic year → classes → sections) and enroll children into sections.

## Features (planned — finalize at M2 start)

- **F-M2-1** Activate structure tab — currently disabled placeholder; M2 makes it real
- **F-M2-2** Activate Children tab — currently disabled placeholder; M2 makes it real
- **F-M2-3** Academic year management — create academic year, link year to school. M2 supports current year only; year switching/progression deferred to M5.
- **F-M2-4** Classes — add/edit classes for a school under the active academic year
- **F-M2-5** Sections — add/edit sections under classes; max-5-children rule visible in UI
- **F-M3-6** Children list & enrollment — add child, assign to section, basic info
- **F-M3-7** Children edit — update info, change section
- **F-M3-8** Children deactivation — soft-delete with mandatory removed_reason
- **F-M3-9** Children reactivation — bring back a previously-deactivated child
- **F-M3-10** Children list filters — by section, status, search


## Major in-scope items

- Foundational academic year (creation only, single active year for M2)
- Full class + section CRUD
- Full child lifecycle (enroll, edit, deactivate, reactivate, list, filter)
- Children tab activated on school detail page

## Major out-of-scope items

- Year progression / year switching (M5)
- Volunteer assignment (M3)
- Slot scheduling (M3)
- Setup completeness checklist (M5 — UX polish, not foundational)
- Activate Structure tab visual (M5 — content shown via Children tab in M2)
- Calendar tab (M5)
- Bulk children import (later)

## Open questions to resolve at M2 start

- Class naming convention — "Class 5", "Grade 5", "5th", or whatever Hasura sends?
- Mandatory child fields vs optional (what's the minimum to enroll)?
- What happens to a section when its assigned children all get deactivated?
- Is academic year per-school or platform-wide for M2? (Recommend platform-wide single year, simpler.)

> **Detailed M2 spec:** Written when M2 begins.

---

# Milestone 3 — Volunteers + Scheduling

**Status:** Not started
**Production goal:** A CO can assign volunteers to a school and build the teaching schedule (slots + slot-class assignments).

## Features (planned — finalize at M3 start)

- **F-M3-6** Volunteer assignment — assign a volunteer (existing user) to a school
- **F-M3-7** Volunteer removal — remove from school, basic cascade handling
- **F-M3-8** CHO scope activation — CHO users now see schools where they have an active assignment
- **F-M3-11** Activate Volunteers tab — currently disabled placeholder
- **F-M4-1** Slot creation — define a time slot (day, start time, end time) for a school
- **F-M4-2** Slot edit and delete — change times; soft-delete slots
- **F-M4-3** Slot-class assignment — assign section + subject + 1-2 volunteers to a slot
- **F-M4-4** Schedule validation — no overlapping slots for same volunteer, vol1 ≠ vol2, valid section/volunteer
- **F-M4-6** Schedule view — visual representation of the week's slots and assignments
- **F-M4-7** Activate Slots tab — currently disabled placeholder

## Major in-scope items

- Volunteer-to-school assignment (creation + removal)
- CHO RBAC scope becomes real (was empty in M1, M2)
- Full slot CRUD (create, edit, delete)
- Slot-class composition (section + subject + volunteers)
- All scheduling business rules enforced (volunteer count, overlaps, etc.)
- Volunteers tab + Slots tab activated

## Major out-of-scope items

- Move volunteer between slot-classes (M4 — fast-follow feature)
- Volunteer-deactivation alert (M4)
- Cross-school volunteer conflict (M5)
- Recurring slot templates (later)
- Substitute volunteer workflow (later)
- Volunteer performance metrics (later)

## Open questions to resolve at M3 start

- Volunteer-to-school enforcement: 1 volunteer per school confirmed in business rules — does this apply per academic year or forever?
- Slot duration constraints — minimum/maximum length?
- Subjects: predefined list or free-text?
- Time zone handling — all slots in IST, or user-locale aware?

> **Detailed M3 spec:** Written when M3 begins.

---

# Milestone 4 — Calendar + Ops Follow-up + Hasura Webhooks

**Status:** Not started
**Production goal:** Schools can record session calendars (start/end dates + holidays). Volunteer reassignment is supported. Hasura sync moves from cron-based to webhook-based for real-time updates.

## Features (planned — finalize at M4 start)

- **F-M2-4** Session dates — start/end dates for the academic session
- **F-M2-5** Holidays — log planned closures and special days
- **F-M3-9** Synced volunteer deactivation alert — surface to admins when a user record gets deactivated via sync
- **F-M4-5** Move volunteer between slot-classes — reassignment workflow
- **F-M5-5** Webhook receiver from Hasura — replace 6h cron with real-time updates (or supplement: webhook + safety-net cron)
- **F-M5-9** Field-level sync diff — track which fields changed between sync runs (foundational for the webhook flow)

## Major in-scope items

- Session calendar (dates + holidays — small but foundational)
- Volunteer reassignment between slot-classes
- Reactive ops: alert admins when sync deactivates a volunteer with active assignments
- Hasura webhook integration — real-time data updates replacing 6h cron polling
- Sync diff tracking — enables targeted re-sync and audit

## Major out-of-scope items

- Setup completeness checklist (M5)
- Activate Calendar tab visually (M5 — data captured here, UI shell in M5)
- Cross-school volunteer conflict detection (M5)
- Sync admin dashboard UI (M5)
- Year progression (M5)

## Open questions to resolve at M4 start

- Webhook authentication from Hasura — what mechanism? Shared secret in headers?
- When webhook arrives, does cron continue as a safety net, or get disabled?
- Holiday categories — single list vs typed (national, regional, school-specific)?
- Sync diff storage — JSONB column on SyncRun, or a separate SyncDiff table?
- Volunteer deactivation alert: in-app notification, email, or both?

> **Detailed M4 spec:** Written when M4 begins.

---

# Milestone 5 — Activation, Polish, Admin Operations

**Status:** Not started
**Production goal:** All deferred UX polish, admin tooling, and the second auth method ship together. The product is feature-complete.

## Features (planned — finalize at M5 start)

- **F-M2-6** Setup completeness checklist — visible on school overview, shows what's still missing
- **F-M2-7** Activate Structure tab — visual shell for class/section structure (data already exists from M2)
- **F-M2-8** Activate Calendar tab — visual shell for session calendar (data already exists from M4)
- **F-M4-8** Cross-school conflict detection — flag if a volunteer is double-booked across schools
- **F-M5-1** Google OAuth sign-in — activate the F01a backend code that's been sitting paused; build frontend Google flow
- **F-M5-2** Sync admin dashboard — see sync run history, status, counts, errors
- **F-M5-3** Manual sync trigger UI — "Sync now" button for admins
- **F-M5-4** Sync health alerts — Sentry/email if sync fails N times in a row
- ~~**F-M5-6** Year progression workflow~~ and ~~**F-M5-7** Year progression preview~~: **moved to M10** (2026-09-28); see `docs/milestones/M10.md`
- **F-M5-8** Volunteer-deactivation admin alerts — admin sees impacted assignments when a volunteer's user record deactivates
- **F-M5-10** Celery + Redis introduction — replace cron-based sync with proper async queue

## Major in-scope items

- Google OAuth (full flow, frontend reactivated)
- Sync admin UI for monitoring and manual triggers
- ~~Year progression flow~~ (moved to M10)
- Celery and Redis for queueing
- All deferred UX polish: setup checklist, tab visuals, conflict detection

## Major out-of-scope items

- Bulk admin operations beyond year progression (defer until needed)
- Multi-tenant admin features — out of scope; single MAD organization only
- Custom sync schedules per environment — assume one global schedule

## Open questions to resolve at M5 start

- ~~Year progression — does it run automatically on a date, or always manual trigger?~~ Resolved in M10: always a manual admin action.
- Hosted-domain restriction on Google OAuth — restrict to `@makeadiff.in` only, or allow any verified domain?
- Should sync dashboard show field-level diffs (already captured in M4's sync diff feature), or just per-run aggregate counts?
- Cross-school conflict — hard block on save, or warning that lets the CO continue?

## Note on M5 size

M5 has 10 features after year progression moved to M10 (2026-09-28); it was the heaviest milestone in this plan. That's the trade-off for ruthlessly deferring polish through M1-M4. By the time M5 starts, you'll have 4 milestones of velocity data and can pace this realistically. M5 may take 2.5 weeks instead of 2; that's expected.

> **Detailed M5 spec:** Written when M5 begins.

---

# Milestone 9 — CSV Data Export for Ops

**Status:** Features complete and verified (2026-09-28). Commit and deploy are pending.
**Production goal:** Any ops user (CO, CHO, admin) can download CSVs of the data they can already see, and every export is audited.

## Features

- **F-M9-1** Export foundation: CSV builder, `ExportLog` audit table, shared Export button
- **F-M9-2** School children roster export (Children tab)
- **F-M9-3** School volunteer roster export (Volunteers tab)
- **F-M9-4** School timetable export (Slots tab)
- **F-M9-5** Schools summary export (Schools list)
- **F-M9-6** All children in scope export (Schools list)
- **F-M9-7** All volunteers in scope export (Schools list)
- **F-M9-8** Ops gap report (Schools list)

## Major out-of-scope items

- Excel/PDF output, scheduled or emailed exports, past academic years, a column picker, import from CSV
- Admin UI for the export audit log, and a log retention policy

> **Detailed M9 spec:** `docs/milestones/M9.md`. Key decisions are in `DECISIONS.md` D031.

---

# Milestone 10 — Year Progression

**Status:** Features complete (2026-09-30); commit, migrations and prod-copy dry run pending
**Production goal:** An admin moves schools into the next academic year in 3–4 clicks, with no developer and no code change, year after year. Children move to each class's admin-set next class and keep their mentoring circles; timetables and term dates are archived for COs to rebuild.

## Features

- **F-M10-1** Class catalog admin: order, next class, open for enrolment (replaces the hard-coded 8th block)
- **F-M10-2** School-year integrity: one active school-year per school; writes and reactivation land in it
- **F-M10-3** Year-scoped reads by the school's own active year (replaces `active_year_slot_q`)
- **F-M10-4** Holidays linked to the school-year (backfilled)
- **F-M10-5** Progression run model, row log and school freeze
- **F-M10-6** Precheck and preview, including graduation marking
- **F-M10-7** Start run (global flip, non-converted cleanup) and execute per school (one transaction each)
- **F-M10-8** Per-school undo until the first new-year write
- **F-M10-9** Admin Year Progression screens (step wizard + Runs tab)

## Major out-of-scope items

- Viewing old years; copying timetables, term dates or holidays forward; multiple programs or subjects; automatic progression; undo after new-year writes

> **Detailed M10 spec:** `docs/milestones/M10.md`

---

## Working with milestones

### At the start of each milestone

- Open the central doc (this file) and confirm scope is still right
- Write the milestone's detailed doc (`docs/milestones/MX.md`) using M1.md as the template
- Build days: 8-10 working days
- Stabilize days: last 3-4 days

### During the milestone

- Use Claude Code plan mode for implementation work
- Come to chat only when stuck on architecture or scope
- Update the milestone doc's "Done log" as work completes

### At the end of each milestone

- All "Definition of production ready" boxes checked
- Update this file's status table
- Brief retrospective: what went faster than expected, what hit blockers, what to carry into the next milestone
- Decide: ship as-is, one extra day of fixes, or something needs to slip to the next milestone

### Don't add scope mid-milestone

If a need surfaces, write it down and address it in the next milestone planning. The 2-week box is a forcing function for "what really matters."

---

## What survived from earlier planning

These docs are still authoritative. Read them when relevant:

- `BUSINESS_RULES.md` — every non-negotiable rule
- `GLOSSARY.md` — terms (CO, CHO, slot, slot-class, etc.)
- `ARCHITECTURE.md` — how the system fits together
- `DECISIONS.md` — past architectural decisions
- `UI_REFERENCE.md` — visual system
- `FRONTEND_ARCHITECTURE.md` — frontend conventions
- `FRONTEND_DECISIONS.md` — frontend decisions

These are deprecated:

- `FEATURE_PLAN.md` — replaced by this file
- `FEATURE_TEMPLATE.md` — replaced by per-milestone feature notes
- `PROGRESS.md` — folded into each milestone's done log
- `F01a-google-oauth-login.md` and `F01b-password-authentication.md` — auth work re-scoped under M1 password and M5 Google

---

## Quick reference — what's already built before M1

State of code as of milestone restart:

- Schema renamed to `mad_sessionops_dev`
- `SoftDeleteBaseModel` and `User`/`UserAuth` models match the multi-auth schema
- 4605 users already in the DB from prior import
- Auth services (`role_helpers`, `complete_google_login`, `refresh_access_token`, `logout`, exceptions) are built and tested — Google-side flow paused
- API endpoints `/api/auth/google/callback`, `/refresh`, `/logout`, `/me` exist
- Single DB user `sessionops_app_user` with full schema permissions

M1 reuses the schema, role helpers, JWT services, refresh, logout, /me. Adds password endpoints. Removes Google callback from M1 routing (kept in code for M5).
