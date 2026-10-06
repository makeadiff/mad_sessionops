"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import CircularProgress from "@mui/material/CircularProgress";
import Skeleton from "@mui/material/Skeleton";
import Link from "next/link";
import { Plus, Calendar, Trash2 } from "lucide-react";
import { api } from "@/lib/api/client";
import { showSuccess, showApiError } from "@/lib/toast/toast";
import { useAppSelector } from "@/lib/redux/hooks";
import { selectUser } from "@/lib/redux/features/auth/authSlice";
import { AdminContent, AdminShell } from "./AdminShell";
import {
  DialogShell,
  FieldLabel,
  Notice,
  PageIntro,
  Pill,
  dangerButtonSx,
  fieldSx,
  linkButtonSx,
  primaryButtonSx,
  secondaryButtonSx,
} from "./adminUi";

// ── Colors ─────────────────────────────────────────────────────────────────────
const BORDER = "#E2E8F0";
const MUTED = "#94A3B8";
const HEADING = "#1E293B";

interface AcademicYear {
  academicYearId: number;
  label: string;
  isActive: boolean;
  schoolCount: number;
  canRemove: boolean;
}

interface RawYear {
  academic_year_id: number;
  label: string;
  is_active: boolean;
  school_count?: number;
  can_remove?: boolean;
}

function mapYear(raw: RawYear): AcademicYear {
  return {
    academicYearId: raw.academic_year_id,
    label: raw.label,
    isActive: raw.is_active,
    schoolCount: raw.school_count ?? 0,
    canRemove: raw.can_remove ?? false,
  };
}

/** Full-format check ("2027-2028", not "2027-28"); the server enforces the same. */
export function labelError(label: string): string | null {
  const v = label.trim();
  if (!v) return "Label is required.";
  const m = /^(\d{4})-(\d{4})$/.exec(v);
  if (!m) return "Use the full format with both years, e.g. 2027-2028 (not 2027-28).";
  if (Number(m[2]) !== Number(m[1]) + 1) return "The second year must be one more than the first.";
  return null;
}

/** The inactive year right after the active one — the year schools move into next. */
function nextYearIdOf(years: AcademicYear[]): number | null {
  const active = years.find((y) => y.isActive);
  if (!active) return null;
  const want = Number(active.label.split("-")[0]) + 1;
  return (
    years.find((y) => !y.isActive && Number(y.label.split("-")[0]) === want)?.academicYearId ?? null
  );
}

/** The only label the server accepts next: the year after the latest one. */
export function nextYearLabel(years: { label: string }[]): string {
  const starts = years.map((y) => Number(y.label.split("-")[0])).filter((n) => !Number.isNaN(n));
  const start = starts.length ? Math.max(...starts) + 1 : new Date().getFullYear();
  return `${start}-${start + 1}`;
}

async function fetchAllYears(): Promise<AcademicYear[]> {
  const raw = await api.get<RawYear[]>("/academic-years/admin/");
  return raw.map(mapYear);
}

async function createYear(label: string): Promise<AcademicYear> {
  const raw = await api.post<RawYear>("/academic-years/admin/", { label });
  return mapYear(raw);
}

async function removeYear(academicYearId: number): Promise<void> {
  await api.delete(`/academic-years/admin/${academicYearId}/`);
}

// ── Create modal ───────────────────────────────────────────────────────────────

function CreateYearModal({
  open,
  suggested,
  onClose,
  onCreated,
}: {
  open: boolean;
  suggested: string;
  onClose: () => void;
  onCreated: (year: AcademicYear) => void;
}) {
  // Remounted (key) on every open, so this prefills the next year each time.
  const [label, setLabel] = useState(suggested);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit() {
    const trimmed = label.trim();
    const invalid = labelError(trimmed);
    if (invalid) {
      setError(invalid);
      return;
    }
    setSaving(true);
    try {
      const year = await createYear(trimmed);
      showSuccess(`Academic year "${year.label}" created.`);
      onCreated(year);
      setLabel("");
      onClose();
    } catch (err) {
      showApiError(err);
    } finally {
      setSaving(false);
    }
  }

  function handleClose() {
    if (saving) return;
    setLabel("");
    setError("");
    onClose();
  }

  return (
    <DialogShell
      open={open}
      onClose={handleClose}
      title="Create Academic Year"
      actions={
        <>
          <Button
            variant="outlined"
            onClick={handleClose}
            disabled={saving}
            size="small"
            sx={secondaryButtonSx}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleSubmit}
            disabled={saving || labelError(label) !== null}
            size="small"
            sx={{ ...primaryButtonSx, minWidth: 96 }}
          >
            {saving ? <CircularProgress size={14} color="inherit" /> : "Create"}
          </Button>
        </>
      }
    >
      <FieldLabel htmlFor="year-label" required>
        Label
      </FieldLabel>
      <TextField
        id="year-label"
        value={label}
        onChange={(e) => {
          setLabel(e.target.value);
          setError("");
        }}
        error={!!(error || (label.trim() && labelError(label)))}
        helperText={
          error ||
          (label.trim() && labelError(label)) ||
          `Only the year after the latest one can be added (${suggested}).`
        }
        size="small"
        fullWidth
        sx={fieldSx}
        placeholder={suggested}
      />
      <Typography sx={{ fontSize: "12px", color: MUTED, mt: 1.5, lineHeight: 1.5 }}>
        The new year starts inactive. It becomes active when the first Year Progression run into it
        starts.
      </Typography>
    </DialogShell>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export function AcademicYearsPage() {
  const user = useAppSelector(selectUser);
  const [years, setYears] = useState<AcademicYear[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [removing, setRemoving] = useState<AcademicYear | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const reload = () => setReloadKey((k) => k + 1);

  const ADMIN_ROLES = ["Function Lead", "Project Lead", "Project Associate", "CXO"];
  const isAdmin = ADMIN_ROLES.some((r) => user?.role?.includes(r));

  useEffect(() => {
    if (!isAdmin) return;
    fetchAllYears()
      .then(setYears)
      .catch(showApiError)
      .finally(() => setLoading(false));
  }, [isAdmin, reloadKey]);

  // "Next" = the year right after the active one (where progression moves schools).
  const nextYearId = nextYearIdOf(years);

  async function confirmRemove() {
    if (!removing) return;
    setRemoveBusy(true);
    try {
      await removeYear(removing.academicYearId);
      showSuccess(`Academic year "${removing.label}" removed.`);
      setRemoving(null);
      reload();
    } catch (err) {
      showApiError(err);
    } finally {
      setRemoveBusy(false);
    }
  }

  if (!isAdmin) {
    return (
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "100vh",
        }}
      >
        <Typography sx={{ fontSize: "16px", fontWeight: 600, color: HEADING }}>
          Access denied
        </Typography>
        <Typography sx={{ fontSize: "14px", color: MUTED, mt: 0.5 }}>
          This page is restricted to administrators.
        </Typography>
      </Box>
    );
  }

  return (
    <AdminShell active="academic-years" title="Academic Years">
      <AdminContent>
        <PageIntro
          description="Platform-wide academic years. Only one is active at a time, and you can only add the year after the latest one."
          actions={
            <Button
              variant="contained"
              size="small"
              startIcon={<Plus size={14} />}
              onClick={() => setCreateOpen(true)}
              sx={primaryButtonSx}
            >
              Create Year
            </Button>
          }
        />

        <Box sx={{ mb: 2 }}>
          <Notice tone="info">
            There is no manual switch. A new year becomes active when the first{" "}
            <Link href="/admin/progression" style={{ color: "inherit", fontWeight: 600 }}>
              Year Progression
            </Link>{" "}
            run into it starts. Schools then move into it as each one is progressed.
          </Notice>
        </Box>

        {/* List */}
        <Box
          sx={{
            border: `1px solid ${BORDER}`,
            borderRadius: "10px",
            overflow: "hidden",
            bgcolor: "#fff",
          }}
        >
          {loading ? (
            [1, 2, 3].map((i) => (
              <Box
                key={i}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 2,
                  px: 3,
                  py: 2,
                  borderBottom: `1px solid ${BORDER}`,
                }}
              >
                <Skeleton variant="rounded" width={36} height={36} sx={{ borderRadius: "8px" }} />
                <Box sx={{ flex: 1 }}>
                  <Skeleton width={120} height={16} />
                </Box>
                <Skeleton width={60} height={22} sx={{ borderRadius: "11px" }} />
              </Box>
            ))
          ) : years.length === 0 ? (
            <Box sx={{ py: 6, textAlign: "center" }}>
              <Typography sx={{ fontSize: "14px", color: MUTED }}>
                No academic years found.
              </Typography>
            </Box>
          ) : (
            years.map((year) => (
              <Box
                key={year.academicYearId}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 2,
                  px: 3,
                  py: 2,
                  borderBottom: `1px solid ${BORDER}`,
                  "&:last-child": { borderBottom: "none" },
                }}
              >
                <Box
                  sx={{
                    width: 36,
                    height: 36,
                    borderRadius: "8px",
                    bgcolor: year.isActive ? "#EFF6FF" : "#F1F5F9",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  <Calendar
                    size={16}
                    strokeWidth={1.75}
                    color={year.isActive ? "#2563EB" : MUTED}
                  />
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ fontSize: "14px", fontWeight: 600, color: HEADING }}>
                    {year.label}
                  </Typography>
                  <Typography sx={{ fontSize: "12px", color: MUTED }}>
                    {year.schoolCount
                      ? `Used by ${year.schoolCount} ${year.schoolCount === 1 ? "school" : "schools"}`
                      : "Not used by any school yet"}
                  </Typography>
                </Box>
                {year.academicYearId === nextYearId && <Pill label="Next" tone="info" />}
                <Pill
                  label={year.isActive ? "Active" : "Inactive"}
                  tone={year.isActive ? "success" : "neutral"}
                />
                {year.canRemove && (
                  <Button
                    size="small"
                    startIcon={<Trash2 size={13} />}
                    onClick={() => setRemoving(year)}
                    sx={{ ...linkButtonSx, color: "#DC2626", "&:hover": { bgcolor: "#FEF2F2" } }}
                    aria-label={`Remove ${year.label}`}
                  >
                    Remove
                  </Button>
                )}
              </Box>
            ))
          )}
        </Box>

        <CreateYearModal
          key={createOpen ? "open" : "closed"}
          open={createOpen}
          suggested={nextYearLabel(years)}
          onClose={() => setCreateOpen(false)}
          onCreated={() => reload()}
        />

        <DialogShell
          open={removing !== null}
          onClose={() => !removeBusy && setRemoving(null)}
          title={`Remove ${removing?.label ?? ""}?`}
          subtitle="No school uses this year yet."
          actions={
            <>
              <Button
                variant="outlined"
                size="small"
                onClick={() => setRemoving(null)}
                disabled={removeBusy}
                sx={secondaryButtonSx}
              >
                Cancel
              </Button>
              <Button
                variant="outlined"
                size="small"
                onClick={confirmRemove}
                disabled={removeBusy}
                sx={{ ...dangerButtonSx, minWidth: 96 }}
              >
                {removeBusy ? <CircularProgress size={14} color="inherit" /> : "Remove"}
              </Button>
            </>
          }
        >
          <Typography sx={{ fontSize: "13px", color: "#475569", lineHeight: 1.6 }}>
            Use this to undo a year added by mistake. You can add it again later.
          </Typography>
        </DialogShell>
      </AdminContent>
    </AdminShell>
  );
}
