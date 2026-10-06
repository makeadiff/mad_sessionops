import { api } from "../client";

// M9 CSV exports. Each download is built server-side and scoped to what the
// user can view; the backend supplies the real filename via Content-Disposition,
// so the filenames here are only fallbacks.

/** Drop empty values so optional filters aren't sent as `?search=` or `?unassigned=false`. */
export function exportParams(
  params: Record<string, string | number | boolean | null | undefined>
): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === false) continue;
    if (value === true) {
      out[key] = "true";
      continue;
    }
    // Strings are sent as-is (not trimmed) so the export matches the list request exactly.
    if (value === "") continue;
    out[key] = value;
  }
  return out;
}

// ── F-M9-2 Children roster ────────────────────────────────────────────────────

export interface ChildrenExportFilters {
  status: "active" | "inactive" | "all";
  search?: string;
  classId?: number | null;
  sectionId?: number | null;
  unassigned?: boolean;
}

export function exportSchoolChildren(schoolId: number, f: ChildrenExportFilters): Promise<void> {
  return api.download(
    `/schools/${schoolId}/exports/children.csv`,
    `children_${schoolId}.csv`,
    exportParams({
      status: f.status,
      search: f.search,
      class_id: f.classId,
      section_id: f.sectionId,
      unassigned: f.unassigned,
    })
  );
}

// ── F-M9-3 Volunteer roster ───────────────────────────────────────────────────

export function exportSchoolVolunteers(schoolId: number): Promise<void> {
  return api.download(`/schools/${schoolId}/exports/volunteers.csv`, `volunteers_${schoolId}.csv`);
}

// ── F-M9-4 Timetable ──────────────────────────────────────────────────────────

export function exportSchoolTimetable(schoolId: number): Promise<void> {
  return api.download(`/schools/${schoolId}/exports/timetable.csv`, `timetable_${schoolId}.csv`);
}

// ── F-M9-5 Schools summary (Schools page; search matches the page's filter) ────

export function exportSchoolsSummary(search?: string): Promise<void> {
  return api.download("/exports/schools.csv", "schools_all.csv", exportParams({ search }));
}

// ── F-M9-6 All children in scope ──────────────────────────────────────────────

export function exportAllChildren(search?: string): Promise<void> {
  return api.download(
    "/exports/children.csv",
    "children_all.csv",
    exportParams({ search, status: "all" })
  );
}

// ── F-M9-7 All volunteers in scope ────────────────────────────────────────────

export function exportAllVolunteers(search?: string): Promise<void> {
  return api.download("/exports/volunteers.csv", "volunteers_all.csv", exportParams({ search }));
}

// ── F-M9-8 Ops gap report ─────────────────────────────────────────────────────

export function exportGapReport(search?: string): Promise<void> {
  return api.download("/exports/gaps.csv", "gaps_all.csv", exportParams({ search }));
}
