# Feature Plan: F-M10-9 — Admin Year Progression screens

**Milestone doc:** `docs/milestones/M10.md` → F-M10-9 (the layout agreed on 2026-09-28 is in the spec)
**Status:** Plan — not started
**Date:** 2026-09-28
**Depends on:** F-M10-5 to F-M10-8 (APIs). The Setup link row comes from F-M10-1

## Overview

A new **Admin → Year Progression** page with two tabs:
- **New run:** a four-step wizard, one job per screen, with details in a side drawer.
- **Runs:** history, per-school status, logs, Retry, Release, Resume and Undo.

The browser drives execution one school per request, so no request is long-running.

## Blast Radius

| Surface | Impact | Notes |
|---|---|---|
| Frontend pages | New | `app/admin/progression/page.tsx` (client, admin guard as in `app/admin/page.tsx`) |
| Frontend components | New | `components/admin/progression/`: `ProgressionPage.tsx` (tabs), `ProgressionWizard.tsx` (stepper + state), `StepSchools.tsx`, `StepPrecheck.tsx`, `StepPreview.tsx`, `StepRun.tsx`, `SchoolDrawer.tsx` (shared by precheck, preview and runs), `GraduationPicker.tsx`, `RunsTab.tsx`, `RunDetail.tsx` |
| Frontend components (modified) | Modified | `AdminPage.tsx` Setup row: + "Year Progression". `AcademicYearsPage.tsx`: a "Next" chip on the target year (derived from `GET eligible-schools` / the target endpoint) |
| Frontend API | New/extended | `lib/api/services/progression.service.ts`: eligibleSchools, precheck, preview, previewChildren, startRun, executeSchool, listRuns, getRun, getRunSchool, retry (= executeSchool), release, undo |
| State | Local | Wizard state is kept in `ProgressionWizard` (`useReducer`). No Redux; nothing is persisted apart from what the server stores (runs) |
| Backend | Small | `GET /api/admin/progression/target-year/`: the resolved target year (id, label) or the reason there isn't one. It's used by step 1 and the Academic Years chip. Admin only; it reuses the F-M10-6 rules |
| Existing tests | Minor | The `AdminPage` test covers the new link row |
| Documentation | Update | UI_REFERENCE.md (a new admin page), M10 Done log |

## Low-Level Design

**Wizard state (`useReducer`):** `{targetYear, selectedIds:Set, precheck:Map<id,Result>, marks:Map<id,{classIds,childIds}>, preview:Map<id,Counts>, runId?, execState:Map<id,Status>}`.

**Step 1 — Schools (`StepSchools`)**
- Shows the resolved target year (or a blocking message, e.g. "Create 2027-2028 in Academic Years first").
- A table of eligible-schools results with search and "select all eligible". Ineligible rows are greyed out, with a reason tooltip.
- Next is enabled when at least one school is selected.

**Step 2 — Precheck (`StepPrecheck`)**
- Calls `POST precheck/` in chunks of 100.
- A summary line (ready · warning · blocked) and a table (School · Status · Issues ›).
- `›` opens `SchoolDrawer` with the blockers and warnings, each with a human message.
- Blocked schools are auto-deselected, with a note. Next is disabled while any selected school is blocked.

**Step 3 — Preview (`StepPreview`)**
- Calls `POST preview/`.
- A table of counts (classes, sections, moving, staying, graduating, volunteers, archived).
- The drawer shows the class moves (`5th → 6th: 40`) and a `GraduationPicker`:
  - class checkboxes for the classes present
  - a searchable, paginated child list (`GET preview/{id}/children/`)
- Changing marks re-previews that school, debounced.

**Step 4 — Run (`StepRun`)**
- A confirmation dialog: "Move N schools to 2027-2028. Timetables and term dates will be archived; COs must rebuild them. Schools are hidden from COs while they're moved."
- Then `startRun` → `runId`, and a loop that calls `executeSchool(runId, id)` **sequentially**, updating each school's row (queued → running → done / failed).
- Failed rows offer **Retry** (execute again) and **Release**.
- A network error leaves the school `queued`, and the loop stops with a "Resume from Runs" message.
- Leaving the page mid-run is allowed; it can be resumed from Runs.

**Runs tab (`RunsTab`, `RunDetail`)**
- **List:** date, started by, from → to, status, and counts by school status.
- **Detail:** per-school rows.
  - `SchoolDrawer` shows the counts, a row-log summary (per table: created and archived), the error, and **Undo** (enabled per `can_undo`, otherwise disabled with `undo_block_reason`), Retry and Release.
  - A **Resume** button runs the same sequential loop over the run's `queued` schools.

**Shared details**
- MUI subpath imports and theme tokens.
- Loading skeletons and explicit error states (frontend CLAUDE.md).
- Toasts via `lib/toast/toast`.
- No business rules in the UI; gating uses server results only.

## Business Rules Enforced (as display; enforcement is server-side)

- Blocked schools can't proceed; undo is available only when `can_undo`; only admins can reach the page.

## Security Review

- The route guard redirects non-admins (ADMIN_ROLES exact match, the same as `/admin`). Every call is admin-checked on the server.
- No sensitive data is shown beyond names and counts (the child picker has no date of birth or contact).

## Testing Strategy

**Frontend — `__tests__/admin/progression/*.test.tsx`** (services mocked)
- **Wizard:**
  - step gating: Next is disabled with no selection and with a blocked school selected
  - blocked schools are auto-deselected
  - the drawer shows blockers and warnings
- **Preview:** class and child marks go into the `startRun` payload; changing marks re-requests the preview.
- **Run:**
  - execute is called once per school, in order
  - a failure shows Retry and Release, and Retry succeeds
  - a network error stops the loop with the resume message
- **Runs:** list and detail render; Resume runs the queued schools; Undo is disabled with its reason when `can_undo=false` and calls the endpoint when true.
- **Guard and nav:** a non-admin is redirected; the AdminPage Setup row shows the Year Progression link.

**Backend:** a test for `GET target-year/` (the cases from F-M10-6's target rules).

**Manual:** the full flow on a prod-data copy (the M10 smoke test): 3 schools, one class graduated, one school undone and re-run.

## Milestones (implementation order)

1. Service module + page shell + tabs + Step 1 and the target-year endpoint.
2. Steps 2–3 with the drawer and graduation picker.
3. Step 4 run loop + Runs tab (Retry, Release, Resume, Undo) + Vitest; full frontend suite; manual smoke on a prod copy.

## Open Questions

- None.
