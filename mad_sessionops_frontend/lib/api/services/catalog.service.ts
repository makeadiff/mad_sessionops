import { api } from "../client";

// F-M10-1 Admin → Classes. Admin-only endpoints (ADMIN_ROLES); the backend enforces it.

export interface AdminClass {
  classId: number;
  classCode: string;
  className: string;
  /** Read-only: derived from the next-class chain on the server. */
  sequence: number;
  nextClassId: number | null;
  nextClassName: string | null;
  openForEnrolment: boolean;
  isActive: boolean;
  inUseCount: number;
}

interface RawAdminClass {
  class_id: number;
  class_code: string;
  class_name: string;
  sequence: number;
  next_class_id: number | null;
  next_class_name: string | null;
  open_for_enrolment: boolean;
  is_active: boolean;
  in_use_count: number;
}

function mapClass(raw: RawAdminClass): AdminClass {
  return {
    classId: raw.class_id,
    classCode: raw.class_code,
    className: raw.class_name,
    sequence: raw.sequence,
    nextClassId: raw.next_class_id,
    nextClassName: raw.next_class_name,
    openForEnrolment: raw.open_for_enrolment,
    isActive: raw.is_active,
    inUseCount: raw.in_use_count,
  };
}

export interface ClassInput {
  classCode: string;
  className: string;
  nextClassId: number | null;
  openForEnrolment: boolean;
}

export type ClassPatch = Partial<ClassInput> & { isActive?: boolean };

function toRaw(input: ClassPatch): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (input.classCode !== undefined) out.class_code = input.classCode;
  if (input.className !== undefined) out.class_name = input.className;
  if (input.nextClassId !== undefined) out.next_class_id = input.nextClassId;
  if (input.openForEnrolment !== undefined) out.open_for_enrolment = input.openForEnrolment;
  if (input.isActive !== undefined) out.is_active = input.isActive;
  return out;
}

export async function fetchAdminClasses(): Promise<AdminClass[]> {
  const raw = await api.get<RawAdminClass[]>("/admin/classes/");
  return raw.map(mapClass);
}

export async function createClass(input: ClassInput): Promise<AdminClass> {
  return mapClass(await api.post<RawAdminClass>("/admin/classes/", toRaw(input)));
}

export async function updateClass(classId: number, patch: ClassPatch): Promise<AdminClass> {
  return mapClass(await api.patch<RawAdminClass>(`/admin/classes/${classId}/`, toRaw(patch)));
}
