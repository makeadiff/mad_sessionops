"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Skeleton from "@mui/material/Skeleton";
import Typography from "@mui/material/Typography";
import { ArrowLeft, ArrowRight, Play } from "lucide-react";
import { fetchAdminClasses } from "@/lib/api/services/catalog.service";
import {
  fetchEligibleSchools,
  precheckSchools,
  previewSchools,
  startRun,
  type EligibleSchool,
  type PrecheckResult,
  type PreviewResult,
} from "@/lib/api/services/progression.service";
import { showApiError } from "@/lib/toast/toast";
import {
  BODY,
  BORDER,
  DialogShell,
  MUTED,
  Notice,
  Pill,
  StepIndicator,
  TH_TEXT,
  TypeToConfirm,
  confirmMatches,
  primaryButtonSx,
  secondaryButtonSx,
} from "../adminUi";
import { StepPrecheck } from "./StepPrecheck";
import { StepPreview, type MarksBySchool } from "./StepPreview";
import { StepRun } from "./StepRun";
import { StepSchools } from "./StepSchools";

const STEPS = ["Choose schools", "Precheck", "Preview", "Run"];

/**
 * F-M10-9 New run: one job per step. All rules are enforced server-side; the
 * wizard only gates navigation on the server's precheck results.
 */
export function ProgressionWizard({ onOpenRuns }: { onOpenRuns?: () => void } = {}) {
  const [activeYear, setActiveYear] = useState<string | null>(null);
  const [schools, setSchools] = useState<EligibleSchool[]>([]);
  const [classIdByName, setClassIdByName] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [step, setStep] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [precheck, setPrecheck] = useState<PrecheckResult[]>([]);
  const [preview, setPreview] = useState<PreviewResult[]>([]);
  const [marks, setMarks] = useState<MarksBySchool>({});
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [runId, setRunId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [eligible, catalog] = await Promise.all([
          fetchEligibleSchools(),
          fetchAdminClasses(),
        ]);
        if (cancelled) return;
        setActiveYear(eligible.activeYearLabel);
        setSchools(eligible.schools);
        setClassIdByName(Object.fromEntries(catalog.map((c) => [c.className, c.classId])));
      } catch (error) {
        showApiError(error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedList = [...selected];
  const marksFor = (ids: number[]) =>
    ids.map((schoolId) => ({
      schoolId,
      graduateClassIds: marks[schoolId]?.classIds ?? [],
      graduateChildIds: marks[schoolId]?.childIds ?? [],
    }));

  const goPrecheck = async () => {
    setBusy(true);
    try {
      const results = await precheckSchools(selectedList);
      setPrecheck(results);
      // Blocked schools can't run: drop them from the selection.
      setSelected(new Set(results.filter((r) => r.status !== "blocked").map((r) => r.schoolId)));
      setStep(1);
    } catch (error) {
      showApiError(error);
    } finally {
      setBusy(false);
    }
  };

  const goPreview = async () => {
    setBusy(true);
    try {
      setPreview(await previewSchools(marksFor(selectedList)));
      setStep(2);
    } catch (error) {
      showApiError(error);
    } finally {
      setBusy(false);
    }
  };

  const changeMarks = async (
    schoolId: number,
    next: { classIds: number[]; childIds: number[] }
  ) => {
    setMarks((prev) => ({ ...prev, [schoolId]: next }));
    try {
      const [updated] = await previewSchools([
        { schoolId, graduateClassIds: next.classIds, graduateChildIds: next.childIds },
      ]);
      setPreview((prev) => prev.map((r) => (r.schoolId === schoolId ? updated : r)));
    } catch (error) {
      showApiError(error);
    }
  };

  const confirmStart = async () => {
    setBusy(true);
    try {
      const run = await startRun(marksFor(selectedList));
      setConfirmOpen(false);
      setRunId(run.runId);
      setStep(3);
    } catch (error) {
      showApiError(error);
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: "10px", bgcolor: "#fff", p: 3 }}>
        <Skeleton width={360} height={22} />
        <Skeleton width="100%" height={160} sx={{ mt: 2 }} variant="rounded" />
      </Box>
    );
  }

  const selectedBlocked = precheck.some((r) => r.status === "blocked" && selected.has(r.schoolId));
  const schoolOf = (id: number) => schools.find((s) => s.schoolId === id);
  const nameOf = (id: number) => schoolOf(id)?.schoolName ?? `School ${id}`;
  const moveOf = (id: number) => {
    const s = schoolOf(id);
    return s?.currentYearLabel && s.targetYearLabel
      ? `${s.currentYearLabel} → ${s.targetYearLabel}`
      : "";
  };
  // The platform's active year follows the newest year any school moves into.
  const start = (label: string | null | undefined) => (label ? Number(label.split("-")[0]) : 0);
  const newestTarget = selectedList
    .map((id) => schoolOf(id)?.targetYearLabel ?? null)
    .reduce<string | null>((best, l) => (start(l) > start(best) ? l : best), null);
  const activates = newestTarget && start(newestTarget) > start(activeYear) ? newestTarget : null;
  const graduatingTotal = preview.reduce((t, r) => t + r.counts.childrenGraduating, 0);
  // One school per run. Type-to-confirm phrase = the school's name.
  const chosen = selectedList[0] ?? null;
  const confirmPhrase = chosen !== null ? nameOf(chosen) : "";

  const footerHint =
    step === 0
      ? chosen !== null
        ? `Selected: ${nameOf(chosen)}`
        : "Choose one school"
      : step === 1
        ? chosen !== null
          ? `${nameOf(chosen)} can continue to preview`
          : "This school is blocked — go Back and choose another"
        : step === 2 && chosen !== null
          ? `${nameOf(chosen)}: ${moveOf(chosen)}`
          : null;

  return (
    <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: "10px", bgcolor: "#fff" }}>
      {/* ── Header: steps + target year ── */}
      <Box
        sx={{
          px: 2.5,
          py: 2,
          borderBottom: `1px solid ${BORDER}`,
          display: "flex",
          alignItems: "center",
          gap: 3,
          flexWrap: "wrap",
        }}
      >
        <Box sx={{ flex: 1, minWidth: 420 }}>
          <StepIndicator steps={STEPS} active={step} />
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Typography sx={{ fontSize: "12px", color: TH_TEXT }}>Active year</Typography>
          <Pill label={activeYear ?? "None"} tone="info" />
        </Box>
      </Box>

      {step === 0 && (
        <Box sx={{ px: 2.5, pt: 2 }}>
          <Notice tone="info">
            Choose one school. It moves one year ahead of its own year (for example 2025-2026 →
            2026-2027). Schools are progressed one at a time; the others stay where they are.
          </Notice>
        </Box>
      )}
      {activates && step < 3 && (
        <Box sx={{ px: 2.5, pt: 2 }}>
          <Notice tone="warning">
            Starting this run will also make <strong>{activates}</strong> the active academic year
            for the whole platform (new schools will join it).
          </Notice>
        </Box>
      )}

      {/* ── Step body ── */}
      <Box sx={{ p: 2.5 }}>
        {step === 0 && <StepSchools schools={schools} selected={selected} onChange={setSelected} />}
        {step === 1 && <StepPrecheck results={precheck} />}
        {step === 2 && (
          <StepPreview
            results={preview}
            marks={marks}
            classIdByName={classIdByName}
            onMarksChange={changeMarks}
          />
        )}
        {step === 3 && runId !== null && (
          <StepRun
            runId={runId}
            schools={selectedList.map((id) => ({ schoolId: id, schoolName: nameOf(id) }))}
            onOpenRuns={onOpenRuns}
          />
        )}
      </Box>

      {/* ── Footer actions ── */}
      {step < 3 && (
        <Box
          sx={{
            px: 2.5,
            py: 1.75,
            borderTop: `1px solid ${BORDER}`,
            bgcolor: "#FAFAFA",
            borderRadius: "0 0 10px 10px",
            display: "flex",
            alignItems: "center",
            gap: 1,
          }}
        >
          <Typography sx={{ fontSize: "12px", color: MUTED, mr: "auto" }}>{footerHint}</Typography>
          {step > 0 && (
            <Button
              variant="outlined"
              size="small"
              startIcon={<ArrowLeft size={14} />}
              onClick={() => setStep(step - 1)}
              disabled={busy}
              sx={secondaryButtonSx}
            >
              Back
            </Button>
          )}
          {step === 0 && (
            <Button
              variant="contained"
              size="small"
              endIcon={
                busy ? <CircularProgress size={12} color="inherit" /> : <ArrowRight size={14} />
              }
              onClick={goPrecheck}
              disabled={busy || selected.size === 0}
              sx={primaryButtonSx}
            >
              Next
            </Button>
          )}
          {step === 1 && (
            <Button
              variant="contained"
              size="small"
              endIcon={
                busy ? <CircularProgress size={12} color="inherit" /> : <ArrowRight size={14} />
              }
              onClick={goPreview}
              disabled={busy || selected.size === 0 || selectedBlocked}
              sx={primaryButtonSx}
            >
              Next
            </Button>
          )}
          {step === 2 && (
            <Button
              variant="contained"
              size="small"
              startIcon={<Play size={13} />}
              onClick={() => {
                setConfirmText("");
                setConfirmOpen(true);
              }}
              disabled={busy || selected.size === 0}
              sx={primaryButtonSx}
            >
              Run progression
            </Button>
          )}
        </Box>
      )}

      <DialogShell
        open={confirmOpen}
        onClose={() => !busy && setConfirmOpen(false)}
        title={`Move ${chosen !== null ? nameOf(chosen) : "this school"} one year ahead?`}
        subtitle={chosen !== null ? moveOf(chosen) : undefined}
        actions={
          <>
            <Button
              variant="outlined"
              size="small"
              onClick={() => setConfirmOpen(false)}
              disabled={busy}
              sx={secondaryButtonSx}
            >
              Cancel
            </Button>
            <Button
              variant="contained"
              size="small"
              onClick={confirmStart}
              disabled={busy || !confirmMatches(confirmText, confirmPhrase)}
              sx={{ ...primaryButtonSx, minWidth: 96 }}
            >
              {busy ? <CircularProgress size={14} color="inherit" /> : "Start"}
            </Button>
          </>
        }
      >
        <Box
          component="ul"
          sx={{ m: 0, pl: 2.25, display: "flex", flexDirection: "column", gap: 0.75 }}
        >
          {[
            "Children move to their next class and keep their sections, which are copied into the new year.",
            "Timetables and term dates are archived — COs rebuild them for the new year.",
            "Schools are hidden from COs and CHOs while they are being moved.",
            graduatingTotal > 0
              ? `${graduatingTotal} child(ren) will be marked as graduated.`
              : null,
          ]
            .filter(Boolean)
            .map((line) => (
              <Typography component="li" key={line} sx={{ fontSize: "13px", color: BODY }}>
                {line}
              </Typography>
            ))}
        </Box>
        <TypeToConfirm
          phrase={confirmPhrase}
          value={confirmText}
          onChange={setConfirmText}
          disabled={busy}
        />
      </DialogShell>
    </Box>
  );
}
