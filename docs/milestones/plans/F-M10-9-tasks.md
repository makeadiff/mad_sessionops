# F-M10-9 Execution Progress

Plan: `docs/milestones/plans/F-M10-9-plan.md`. Not committing; the human commits manually.
**Status:** Complete 2026-09-30. Frontend only; the `GET target-year/` backend endpoint was built in F-M10-6.

## Milestone 1: Service + page shell + Step 1
- [x] `progression.service.ts` += `startRun`, `executeSchool`, `releaseSchool`, `undoSchool`, `listRuns`, `getRun`, `getRunSchool` (+ types)
- [x] `app/admin/progression/page.tsx`: admin guard (exact ADMIN_ROLES, CXO redirected), same as `/admin`
- [x] `components/admin/progression/ProgressionPage.tsx`: back link, **New run | Runs** tabs
- [x] `ProgressionWizard.tsx`:
  - loads the target year, eligible schools and the class catalog
  - MUI Stepper: Schools → Precheck → Preview → Run
  - "no target year" message
- [x] `StepSchools.tsx`: search, select-all-eligible; ineligible rows are disabled with a reason tooltip
- [x] AdminPage Setup link **Year Progression**; Academic Years **Next** chip on the year the next run would activate (from `target-year`, only when it flips the global year)

## Milestone 2: Precheck + preview
- [x] `StepPrecheck.tsx`:
  - summary (ready · warning · blocked) and per-school rows; the **drawer** shows blockers and warnings
  - blocked schools are auto-deselected; Next is disabled while any selected school is blocked
- [x] `StepPreview.tsx`:
  - count columns (classes, sections, moving, staying, graduating, volunteers, archived)
  - the drawer shows class moves, added classes, warnings, and the **GraduationPicker**
  - changing marks re-previews that school
- [x] `GraduationPicker.tsx`:
  - whole-class checkboxes, mapping class names to catalog ids from `fetchAdminClasses`
  - child search, debounced and paginated with "Load more"; name, class and section only
- [x] `shared.tsx`: status chips, `SchoolDrawer`, `IssueList`

## Milestone 3: Run + Runs tab
- [x] `useExecuteLoop.ts`:
  - runs schools **one request at a time**
  - a school's failure is recorded and the loop continues
  - a request or network error **stops the loop** and leaves the rest queued, with a "Resume from the Runs tab" message
- [x] `StepRun.tsx`:
  - a confirmation dialog (timetable and term dates archived; schools hidden from COs and CHOs while they move) comes before it
  - live statuses; **Retry** and **Release** on failed schools
- [x] `RunsTab.tsx` / `RunDetail`:
  - runs list; run detail with **Resume (N queued)**
  - the school drawer shows the error and a row-log summary
  - **Undo** is enabled from `can_undo`, or disabled with the reason
  - Retry and Release for failed schools
- [x] Vitest (12):
  - `__tests__/admin/progression/ProgressionWizard.test.tsx` (5): no target; ineligible disabled and Next gated; blocked auto-deselect, drawer blockers, only ready schools previewed; graduation marks passed to Start, sequential execute, failure shows Retry/Release; network error stops with the Resume message
  - `RunsTab.test.tsx` (4): list; Resume executes queued schools in order; Undo disabled with reason and the row-log summary; Undo calls the endpoint
  - `AdminProgressionRoute.test.tsx` (2): CXO redirected; admin renders
  - `AdminSetupLinks.test.tsx` updated (+1 assertion for the Year Progression link)
- [x] **Full frontend suite: 267 passed (35 files).** The first run had the known CalendarTab 1s-`waitFor` flake (5 tests, calendar untouched); the re-run was clean.
- [x] Lint and typecheck on all new and changed files: clean. The remaining ESLint errors in `__tests__/admin` are in untouched files: `AdminPage`, `DataSyncTab`, `RealtimeEventsTab`.

## Deviations
- **`useExecuteLoop`** is a shared hook, so the Run step and Runs-tab Resume use the same one-at-a-time logic. The plan had separate components.
- **Graduation class ids** come from the admin class catalog (name → id), because preview counts carry class names.
- **Typing fix in F-M10-1's test:** `AdminClassesRoute.test.tsx`'s `any` selector typing was fixed together with the new route test.

## Manual check (the human does this)
- [ ] On a prod-data copy, with migrations 0032–0038 applied:
  - Admin → Year Progression: select the 2025-26 schools, then precheck, preview (mark a class to graduate) and run
  - check that children moved and COs saw the banner
  - undo one school, then re-run it

## Blockers
- None
