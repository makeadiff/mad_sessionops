import { api } from "../client";

// M10 Year Progression admin API (ADMIN_ROLES only; the backend enforces it).
// F-M10-6: eligibility, precheck, preview, graduation child picker. Each school
// moves from its own year to the year after it (no run-wide target year).
// F-M10-7/8: runs, execute, release, undo. The screens are F-M10-9.

// ── Types ─────────────────────────────────────────────────────────────────────

export interface EligibleSchool {
  schoolId: number;
  schoolName: string;
  city: string | null;
  currentYearLabel: string | null;
  /** The year after the school's own — where this school would move. */
  targetYearLabel: string | null;
  /** How far the school's year trails the active year (0 = on it). */
  yearsBehind: number;
  eligible: boolean;
  reason: string | null;
  reasonMessage: string | null;
}

export interface Issue {
  code: string;
  message: string;
}

export type PrecheckStatus = "ready" | "warning" | "blocked";

export interface EligibleSchools {
  activeYearLabel: string | null;
  schools: EligibleSchool[];
}

export interface PrecheckResult {
  schoolId: number;
  schoolName: string;
  currentYearLabel: string | null;
  targetYearLabel: string | null;
  status: PrecheckStatus;
  blockers: Issue[];
  warnings: Issue[];
}

export interface PreviewCounts {
  schoolClassesCopied: number;
  schoolClassesAdded: string[];
  sectionsCopied: number;
  childrenMoving: { from: string; to: string; n: number }[];
  childrenStaying: { class: string; n: number }[];
  childrenGraduating: number;
  volunteersCarried: number;
  archiveCounts: Record<string, number>;
}

export interface PreviewResult extends PrecheckResult {
  counts: PreviewCounts;
}

export interface GraduationMarks {
  schoolId: number;
  graduateClassIds: number[];
  graduateChildIds: number[];
}

export interface PreviewChild {
  childId: number;
  firstName: string;
  lastName: string;
  classId: number | null;
  className: string | null;
  sectionName: string | null;
}

export interface PreviewChildrenPage {
  total: number;
  page: number;
  pageSize: number;
  results: PreviewChild[];
}

// ── Raw shapes (snake_case) ───────────────────────────────────────────────────

interface RawIssue {
  code: string;
  message: string;
}

interface RawPrecheck {
  school_id: number;
  school_name: string;
  current_year_label: string | null;
  target_year_label: string | null;
  status: PrecheckStatus;
  blockers: RawIssue[];
  warnings: RawIssue[];
}

interface RawPreview extends RawPrecheck {
  counts: {
    school_classes_copied: number;
    school_classes_added: string[];
    sections_copied: number;
    children_moving: { from: string; to: string; n: number }[];
    children_staying: { class: string; n: number }[];
    children_graduating: number;
    volunteers_carried: number;
    archive_counts: Record<string, number>;
  };
}

function mapPrecheck(raw: RawPrecheck): PrecheckResult {
  return {
    schoolId: raw.school_id,
    schoolName: raw.school_name,
    currentYearLabel: raw.current_year_label,
    targetYearLabel: raw.target_year_label,
    status: raw.status,
    blockers: raw.blockers,
    warnings: raw.warnings,
  };
}

function mapPreview(raw: RawPreview): PreviewResult {
  const c = raw.counts;
  return {
    ...mapPrecheck(raw),
    counts: {
      schoolClassesCopied: c.school_classes_copied,
      schoolClassesAdded: c.school_classes_added,
      sectionsCopied: c.sections_copied,
      childrenMoving: c.children_moving,
      childrenStaying: c.children_staying,
      childrenGraduating: c.children_graduating,
      volunteersCarried: c.volunteers_carried,
      archiveCounts: c.archive_counts,
    },
  };
}

// ── Calls ─────────────────────────────────────────────────────────────────────

const BASE = "/admin/progression";
/** The backend accepts at most this many schools per precheck/preview call. */
export const PROGRESSION_CHUNK = 100;

export async function fetchEligibleSchools(): Promise<EligibleSchools> {
  const raw = await api.get<{
    active_year_label: string | null;
    schools: {
      school_id: number;
      school_name: string;
      city: string | null;
      current_year_label: string | null;
      target_year_label: string | null;
      years_behind: number;
      eligible: boolean;
      reason: string | null;
      reason_message: string | null;
    }[];
  }>(`${BASE}/eligible-schools/`);
  return {
    activeYearLabel: raw.active_year_label,
    schools: raw.schools.map((r) => ({
      schoolId: r.school_id,
      schoolName: r.school_name,
      city: r.city,
      currentYearLabel: r.current_year_label,
      targetYearLabel: r.target_year_label,
      yearsBehind: r.years_behind,
      eligible: r.eligible,
      reason: r.reason,
      reasonMessage: r.reason_message,
    })),
  };
}

function chunks<T>(items: T[], size = PROGRESSION_CHUNK): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

/** Prechecks any number of schools, 100 per request (the backend limit). */
export async function precheckSchools(schoolIds: number[]): Promise<PrecheckResult[]> {
  const results: PrecheckResult[] = [];
  for (const part of chunks(schoolIds)) {
    const raw = await api.post<RawPrecheck[]>(`${BASE}/precheck/`, { school_ids: part });
    results.push(...raw.map(mapPrecheck));
  }
  return results;
}

/** Previews any number of schools with their graduation marks, 100 per request. */
export async function previewSchools(schools: GraduationMarks[]): Promise<PreviewResult[]> {
  const results: PreviewResult[] = [];
  for (const part of chunks(schools)) {
    const raw = await api.post<RawPreview[]>(`${BASE}/preview/`, {
      schools: part.map((s) => ({
        school_id: s.schoolId,
        graduate_class_ids: s.graduateClassIds,
        graduate_child_ids: s.graduateChildIds,
      })),
    });
    results.push(...raw.map(mapPreview));
  }
  return results;
}

export async function fetchPreviewChildren(
  schoolId: number,
  opts: { classId?: number | null; search?: string; page?: number; pageSize?: number } = {}
): Promise<PreviewChildrenPage> {
  const params: Record<string, string | number> = {};
  if (opts.classId) params.class_id = opts.classId;
  if (opts.search && opts.search.trim()) params.search = opts.search.trim();
  if (opts.page) params.page = opts.page;
  if (opts.pageSize) params.page_size = opts.pageSize;
  const raw = await api.get<{
    total: number;
    page: number;
    page_size: number;
    results: {
      child_id: number;
      first_name: string;
      last_name: string;
      class_id: number | null;
      class_name: string | null;
      section_name: string | null;
    }[];
  }>(`${BASE}/preview/${schoolId}/children/`, { params });
  return {
    total: raw.total,
    page: raw.page,
    pageSize: raw.page_size,
    results: raw.results.map((r) => ({
      childId: r.child_id,
      firstName: r.first_name,
      lastName: r.last_name,
      classId: r.class_id,
      className: r.class_name,
      sectionName: r.section_name,
    })),
  };
}

// ── Runs (F-M10-7), release (F-M10-5), undo (F-M10-8) ─────────────────────────

export type SchoolRunStatus = "queued" | "running" | "completed" | "failed" | "undone" | "released";
export type RunStatus = "in_progress" | "completed" | "completed_with_failures";

export interface YearMove {
  /** e.g. "2025-2026 → 2026-2027" */
  label: string;
  schools: number;
}

export interface Run {
  runId: number;
  status: RunStatus;
  /** Each school moves from its own year, so one run can hold several moves. */
  yearMoves: YearMove[];
  startedByName: string;
  startedAt: string;
  finishedAt: string | null;
  cleanup: Record<string, unknown>;
  schoolCounts: Partial<Record<SchoolRunStatus, number>>;
}

export interface RunSchool {
  schoolProgressionId: number;
  runId: number;
  schoolId: number;
  schoolName: string | null;
  fromYearLabel: string;
  toYearLabel: string | null;
  status: SchoolRunStatus;
  error: string | null;
  counts: Record<string, unknown>;
  warnings: string[];
  graduateClassIds: number[];
  graduateChildIds: number[];
  startedAt: string | null;
  finishedAt: string | null;
  canUndo: boolean;
  undoBlockReason: string | null;
}

export interface RunDetail extends Run {
  schools: RunSchool[];
}

export interface RunSchoolDetail extends RunSchool {
  rowLog: { created?: Record<string, number>; archived?: Record<string, number> };
}

/** Result of executing / releasing / undoing one school. */
export interface SchoolResult {
  schoolId: number;
  status: SchoolRunStatus;
  error: string | null;
}

interface RawRun {
  run_id: number;
  status: RunStatus;
  year_moves: YearMove[];
  started_by_name: string;
  started_at: string;
  finished_at: string | null;
  cleanup: Record<string, unknown>;
  school_counts: Partial<Record<SchoolRunStatus, number>>;
}

interface RawRunSchool {
  school_progression_id: number;
  run_id: number;
  school_id: number;
  school_name?: string | null;
  from_year_label?: string;
  to_year_label?: string | null;
  status: SchoolRunStatus;
  error: string | null;
  counts: Record<string, unknown>;
  warnings: string[];
  graduate_class_ids?: number[];
  graduate_child_ids?: number[];
  started_at: string | null;
  finished_at: string | null;
  can_undo?: boolean;
  undo_block_reason?: string | null;
}

function mapRun(r: RawRun): Run {
  return {
    runId: r.run_id,
    status: r.status,
    yearMoves: r.year_moves ?? [],
    startedByName: r.started_by_name,
    startedAt: r.started_at,
    finishedAt: r.finished_at,
    cleanup: r.cleanup,
    schoolCounts: r.school_counts,
  };
}

function mapRunSchool(r: RawRunSchool): RunSchool {
  return {
    schoolProgressionId: r.school_progression_id,
    runId: r.run_id,
    schoolId: r.school_id,
    schoolName: r.school_name ?? null,
    fromYearLabel: r.from_year_label ?? "",
    toYearLabel: r.to_year_label ?? null,
    status: r.status,
    error: r.error,
    counts: r.counts,
    warnings: r.warnings,
    graduateClassIds: r.graduate_class_ids ?? [],
    graduateChildIds: r.graduate_child_ids ?? [],
    startedAt: r.started_at,
    finishedAt: r.finished_at,
    canUndo: r.can_undo ?? false,
    undoBlockReason: r.undo_block_reason ?? null,
  };
}

function mapResult(r: RawRunSchool): SchoolResult {
  return { schoolId: r.school_id, status: r.status, error: r.error };
}

/** Start: moves the active year forward if needed, queues and freezes the schools. */
export async function startRun(schools: GraduationMarks[]): Promise<Run> {
  const raw = await api.post<RawRun>(`${BASE}/runs/`, {
    schools: schools.map((s) => ({
      school_id: s.schoolId,
      graduate_class_ids: s.graduateClassIds,
      graduate_child_ids: s.graduateChildIds,
    })),
  });
  return mapRun(raw);
}

/** Progress one school (one backend transaction). Called once per school, in order. */
export async function executeSchool(runId: number, schoolId: number): Promise<SchoolResult> {
  return mapResult(
    await api.post<RawRunSchool>(`${BASE}/runs/${runId}/schools/${schoolId}/execute/`)
  );
}

export async function releaseSchool(runId: number, schoolId: number): Promise<SchoolResult> {
  return mapResult(
    await api.post<RawRunSchool>(`${BASE}/runs/${runId}/schools/${schoolId}/release/`)
  );
}

export async function undoSchool(runId: number, schoolId: number): Promise<SchoolResult> {
  return mapResult(await api.post<RawRunSchool>(`${BASE}/runs/${runId}/schools/${schoolId}/undo/`));
}

export async function listRuns(): Promise<Run[]> {
  return (await api.get<RawRun[]>(`${BASE}/runs/`)).map(mapRun);
}

export async function getRun(runId: number): Promise<RunDetail> {
  const raw = await api.get<RawRun & { schools: RawRunSchool[] }>(`${BASE}/runs/${runId}/`);
  return { ...mapRun(raw), schools: raw.schools.map(mapRunSchool) };
}

export async function getRunSchool(runId: number, schoolId: number): Promise<RunSchoolDetail> {
  const raw = await api.get<RawRunSchool & { row_log: RunSchoolDetail["rowLog"] }>(
    `${BASE}/runs/${runId}/schools/${schoolId}/`
  );
  return { ...mapRunSchool(raw), rowLog: raw.row_log };
}
