"use client";

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { ArrowLeft, Play, Undo2 } from "lucide-react";
import {
  getRun,
  getRunSchool,
  listRuns,
  releaseSchool,
  undoSchool,
  type Run,
  type RunDetail as RunDetailType,
  type RunSchoolDetail,
} from "@/lib/api/services/progression.service";
import { showApiError, showSuccess } from "@/lib/toast/toast";
import {
  BORDER,
  DialogShell,
  EmptyRow,
  HEADING,
  HeadRow,
  KeyValue,
  LoadingRows,
  MUTED,
  Notice,
  PanelHeading,
  TableShell,
  TypeToConfirm,
  bodyRowSx,
  cellSx,
  confirmMatches,
  dangerButtonSx,
  linkButtonSx,
  nameCellSx,
  primaryButtonSx,
  secondaryButtonSx,
} from "../adminUi";
import { RunChip, RunStatusChip, SchoolDrawer } from "./shared";
import { useExecuteLoop } from "./useExecuteLoop";

function fmt(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const RUN_COLUMNS = ["Run", "Years", "Started", "By", "Status", "Schools", ""];

export function RunsTab() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [openRunId, setOpenRunId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRuns(await listRuns());
    } catch (error) {
      showApiError(error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (openRunId !== null) {
    return (
      <RunDetail
        runId={openRunId}
        onBack={() => {
          setOpenRunId(null);
          load();
        }}
      />
    );
  }

  return (
    <TableShell>
      <Table size="small">
        <TableHead>
          <HeadRow columns={RUN_COLUMNS} />
        </TableHead>
        <TableBody>
          {loading ? (
            <LoadingRows cols={RUN_COLUMNS.length} rows={3} />
          ) : runs.length === 0 ? (
            <EmptyRow cols={RUN_COLUMNS.length} message="No progression runs yet." />
          ) : (
            runs.map((r) => (
              <TableRow key={r.runId} sx={bodyRowSx}>
                <TableCell sx={nameCellSx}>#{r.runId}</TableCell>
                <TableCell sx={{ ...cellSx, fontSize: "12px" }}>
                  {r.yearMoves.map((m) => (
                    <Box key={m.label} sx={{ whiteSpace: "nowrap" }}>
                      {m.label}
                      {r.yearMoves.length > 1 ? ` (${m.schools})` : ""}
                    </Box>
                  ))}
                </TableCell>
                <TableCell sx={cellSx}>{fmt(r.startedAt)}</TableCell>
                <TableCell sx={cellSx}>{r.startedByName}</TableCell>
                <TableCell sx={cellSx}>
                  <RunChip status={r.status} />
                </TableCell>
                <TableCell sx={{ ...cellSx, fontSize: "12px" }}>
                  {Object.entries(r.schoolCounts)
                    .map(([k, n]) => `${n} ${k}`)
                    .join(" · ")}
                </TableCell>
                <TableCell sx={cellSx} align="right">
                  <Button size="small" onClick={() => setOpenRunId(r.runId)} sx={linkButtonSx}>
                    Open
                  </Button>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </TableShell>
  );
}

export function RunDetail({ runId, onBack }: { runId: number; onBack: () => void }) {
  const [run, setRun] = useState<RunDetailType | null>(null);
  const [drawer, setDrawer] = useState<RunSchoolDetail | null>(null);
  const [acting, setActing] = useState(false);
  const [confirmUndo, setConfirmUndo] = useState(false);
  const [undoText, setUndoText] = useState("");

  const reload = useCallback(async () => {
    try {
      setRun(await getRun(runId));
    } catch (error) {
      showApiError(error);
    }
  }, [runId]);

  const loop = useExecuteLoop();
  const { state: loopState } = loop;

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    if (loopState === "done" || loopState === "stopped") reload();
  }, [loopState, reload]);

  const openSchool = async (schoolId: number) => {
    try {
      setDrawer(await getRunSchool(runId, schoolId));
    } catch (error) {
      showApiError(error);
    }
  };

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setActing(true);
    try {
      await fn();
      showSuccess(label);
      setConfirmUndo(false);
      setDrawer(null);
      await reload();
    } catch (error) {
      showApiError(error);
    } finally {
      setActing(false);
    }
  };

  if (!run) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
        <CircularProgress size={24} sx={{ color: "#2563EB" }} />
      </Box>
    );
  }
  const queued = run.schools.filter((s) => s.status === "queued").map((s) => s.schoolId);
  const running = loop.state === "running";

  const drawerFooter =
    drawer && (drawer.status === "completed" || drawer.status === "failed") ? (
      drawer.status === "completed" ? (
        <Tooltip title={drawer.canUndo ? "" : (drawer.undoBlockReason ?? "")}>
          <span>
            <Button
              variant="outlined"
              size="small"
              startIcon={<Undo2 size={14} />}
              disabled={!drawer.canUndo || acting}
              onClick={() => {
                setUndoText("");
                setConfirmUndo(true);
              }}
              sx={dangerButtonSx}
            >
              Undo
            </Button>
          </span>
        </Tooltip>
      ) : (
        <>
          <Button
            variant="outlined"
            size="small"
            disabled={acting}
            onClick={() =>
              act("School released on its previous year.", () =>
                releaseSchool(run.runId, drawer.schoolId)
              )
            }
            sx={secondaryButtonSx}
          >
            Release
          </Button>
          <Button
            variant="contained"
            size="small"
            disabled={acting || running}
            onClick={() => {
              setDrawer(null);
              loop.run(run.runId, [drawer.schoolId]);
            }}
            sx={primaryButtonSx}
          >
            Retry
          </Button>
        </>
      )
    ) : undefined;

  return (
    <Box>
      <Button
        size="small"
        startIcon={<ArrowLeft size={13} />}
        onClick={onBack}
        sx={{ ...linkButtonSx, color: "#64748B", mb: 1.5, px: 0.5 }}
      >
        All runs
      </Button>

      <Box
        sx={{
          border: `1px solid ${BORDER}`,
          borderRadius: "10px",
          bgcolor: "#fff",
          px: 2.5,
          py: 2,
          mb: 2,
          display: "flex",
          alignItems: "center",
          gap: 2,
          flexWrap: "wrap",
        }}
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
            <Typography sx={{ fontSize: "15px", fontWeight: 700, color: HEADING }}>
              Run #{run.runId}
            </Typography>
            <RunChip status={run.status} />
          </Box>
          <Typography sx={{ fontSize: "12px", color: MUTED, mt: 0.25 }}>
            {run.yearMoves.map((m) => `${m.label} (${m.schools})`).join(" · ")} · Started{" "}
            {fmt(run.startedAt)} by {run.startedByName}
            {run.finishedAt ? ` · finished ${fmt(run.finishedAt)}` : ""}
          </Typography>
        </Box>
        {queued.length > 0 && (
          <Button
            variant="contained"
            size="small"
            startIcon={
              running ? <CircularProgress size={12} color="inherit" /> : <Play size={13} />
            }
            disabled={running}
            onClick={() => loop.run(run.runId, queued)}
            sx={primaryButtonSx}
          >
            {running ? "Resuming…" : `Resume (${queued.length} queued)`}
          </Button>
        )}
      </Box>

      {loop.stopMessage && (
        <Box sx={{ mb: 2 }}>
          <Notice tone="warning">{loop.stopMessage}</Notice>
        </Box>
      )}

      <TableShell>
        <Table size="small">
          <TableHead>
            <HeadRow columns={["School", "Move", "Status", "Finished", ""]} />
          </TableHead>
          <TableBody>
            {run.schools.map((s) => (
              <TableRow key={s.schoolId} sx={bodyRowSx} data-testid={`detail-row-${s.schoolId}`}>
                <TableCell sx={nameCellSx}>{s.schoolName ?? `School ${s.schoolId}`}</TableCell>
                <TableCell sx={{ ...cellSx, whiteSpace: "nowrap" }}>
                  {s.fromYearLabel} → {s.toYearLabel ?? "—"}
                </TableCell>
                <TableCell sx={cellSx}>
                  <RunStatusChip status={loop.statuses[s.schoolId] ?? s.status} />
                </TableCell>
                <TableCell sx={cellSx}>{fmt(s.finishedAt)}</TableCell>
                <TableCell sx={cellSx} align="right">
                  <Button size="small" onClick={() => openSchool(s.schoolId)} sx={linkButtonSx}>
                    Details
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableShell>

      <SchoolDrawer
        open={drawer !== null}
        title={drawer?.schoolName ?? ""}
        subtitle={drawer ? `${drawer.fromYearLabel} → ${drawer.toYearLabel ?? "—"}` : null}
        onClose={() => setDrawer(null)}
        footer={drawerFooter}
      >
        {drawer && (
          <>
            <Box>
              <RunStatusChip status={drawer.status} />
            </Box>
            {drawer.error && <Notice tone="error">{drawer.error}</Notice>}
            {drawer.status === "completed" && !drawer.canUndo && drawer.undoBlockReason && (
              <Notice tone="info">Undo unavailable: {drawer.undoBlockReason}</Notice>
            )}
            {(["created", "archived"] as const).map((action) =>
              drawer.rowLog[action] && Object.keys(drawer.rowLog[action]!).length > 0 ? (
                <Box key={action}>
                  <PanelHeading>Rows {action}</PanelHeading>
                  {Object.entries(drawer.rowLog[action]!).map(([table, n]) => (
                    <KeyValue key={table} label={table.replace(/_/g, " ")} value={n} />
                  ))}
                </Box>
              ) : null
            )}
          </>
        )}
      </SchoolDrawer>

      <DialogShell
        open={confirmUndo && drawer !== null}
        onClose={() => !acting && setConfirmUndo(false)}
        title={`Undo progression for ${drawer?.schoolName ?? "this school"}?`}
        subtitle={`Moves the school back to ${drawer?.fromYearLabel ?? "its previous year"}.`}
        actions={
          <>
            <Button
              variant="outlined"
              size="small"
              onClick={() => setConfirmUndo(false)}
              disabled={acting}
              sx={secondaryButtonSx}
            >
              Cancel
            </Button>
            <Button
              variant="contained"
              size="small"
              disabled={
                acting ||
                !confirmMatches(undoText, drawer?.schoolName ?? `School ${drawer?.schoolId}`)
              }
              onClick={() =>
                drawer &&
                act("School moved back to its previous year.", () =>
                  undoSchool(run.runId, drawer.schoolId)
                )
              }
              sx={{
                ...primaryButtonSx,
                bgcolor: "#DC2626",
                "&:hover": { bgcolor: "#B91C1C", boxShadow: "none" },
                minWidth: 96,
              }}
            >
              {acting ? <CircularProgress size={14} color="inherit" /> : "Undo progression"}
            </Button>
          </>
        }
      >
        <Typography sx={{ fontSize: "13px", color: "#475569", lineHeight: 1.6 }}>
          Everything this run created for the school is removed, and what it archived (timetable,
          term dates, sections, class placements) is restored. Graduated children become active
          again. The platform&apos;s active academic year does not change.
        </Typography>
        <TypeToConfirm
          phrase={drawer?.schoolName ?? `School ${drawer?.schoolId}`}
          value={undoText}
          onChange={setUndoText}
          disabled={acting}
        />
      </DialogShell>
    </Box>
  );
}
