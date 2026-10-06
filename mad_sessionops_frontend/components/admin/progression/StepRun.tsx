"use client";

import { useEffect } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { releaseSchool, type SchoolRunStatus } from "@/lib/api/services/progression.service";
import { showApiError } from "@/lib/toast/toast";
import {
  BORDER,
  HEADING,
  HeadRow,
  MUTED,
  Notice,
  TableShell,
  bodyRowSx,
  cellSx,
  linkButtonSx,
  nameCellSx,
  secondaryButtonSx,
} from "../adminUi";
import { RunStatusChip } from "./shared";
import { useExecuteLoop } from "./useExecuteLoop";

/** Step ④ after confirmation: executes the run's schools one by one, live. */
export function StepRun({
  runId,
  schools,
  onOpenRuns,
}: {
  runId: number;
  schools: { schoolId: number; schoolName: string }[];
  onOpenRuns?: () => void;
}) {
  const loop = useExecuteLoop();
  const { seed, run } = loop;

  useEffect(() => {
    const initial: Record<number, SchoolRunStatus> = {};
    schools.forEach((s) => (initial[s.schoolId] = "queued"));
    seed(initial);
    run(
      runId,
      schools.map((s) => s.schoolId)
    );
    // Run once for this run id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  const retry = (schoolId: number) => run(runId, [schoolId]);
  const release = async (schoolId: number) => {
    try {
      loop.setOne(await releaseSchool(runId, schoolId));
    } catch (error) {
      showApiError(error);
    }
  };

  const statuses = Object.values(loop.statuses);
  const done = statuses.filter((s) => s === "completed").length;
  const failed = statuses.filter((s) => s === "failed").length;
  const finished = statuses.filter((s) => s !== "queued" && s !== "running").length;
  const running = loop.state === "running";
  const pct = schools.length ? Math.round((finished / schools.length) * 100) : 0;

  return (
    <Box>
      <Box
        sx={{
          border: `1px solid ${BORDER}`,
          borderRadius: "10px",
          px: 2,
          py: 1.75,
          mb: 2,
          display: "flex",
          alignItems: "center",
          gap: 2,
        }}
      >
        <Box sx={{ flex: 1 }}>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mb: 1 }}>
            <Typography sx={{ fontSize: "14px", fontWeight: 700, color: HEADING }}>
              Run #{runId}
            </Typography>
            <Typography sx={{ fontSize: "12px", color: MUTED }} data-testid="run-summary">
              {done} of {schools.length} done{failed ? ` · ${failed} failed` : ""}
              {running ? " · running…" : ""}
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={pct}
            sx={{
              height: 6,
              borderRadius: 3,
              bgcolor: "#F1F5F9",
              "& .MuiLinearProgress-bar": {
                borderRadius: 3,
                bgcolor: failed ? "#F59E0B" : "#16A34A",
              },
            }}
          />
        </Box>
        {!running && onOpenRuns && (
          <Button variant="outlined" size="small" onClick={onOpenRuns} sx={secondaryButtonSx}>
            View in Runs
          </Button>
        )}
      </Box>

      {loop.stopMessage && (
        <Box sx={{ mb: 2 }}>
          <Notice tone="warning">{loop.stopMessage}</Notice>
        </Box>
      )}
      {!running && finished === schools.length && failed === 0 && schools.length > 0 && (
        <Box sx={{ mb: 2 }}>
          <Notice tone="success">
            All schools moved. COs can now set up term dates and timetables for the new year.
          </Notice>
        </Box>
      )}

      <TableShell>
        <Table size="small">
          <TableHead>
            <HeadRow columns={["School", "Status", "Details", ""]} />
          </TableHead>
          <TableBody>
            {schools.map((s) => {
              const status = loop.statuses[s.schoolId] ?? "queued";
              return (
                <TableRow key={s.schoolId} sx={bodyRowSx} data-testid={`run-row-${s.schoolId}`}>
                  <TableCell sx={nameCellSx}>{s.schoolName}</TableCell>
                  <TableCell sx={cellSx}>
                    <RunStatusChip status={status} />
                  </TableCell>
                  <TableCell sx={{ ...cellSx, fontSize: "12px", color: "#DC2626", maxWidth: 360 }}>
                    {status === "failed" ? loop.errors[s.schoolId] : ""}
                  </TableCell>
                  <TableCell sx={cellSx} align="right">
                    {status === "failed" && !running && (
                      <Box sx={{ display: "inline-flex", gap: 0.5 }}>
                        <Button size="small" onClick={() => retry(s.schoolId)} sx={linkButtonSx}>
                          Retry
                        </Button>
                        <Button
                          size="small"
                          onClick={() => release(s.schoolId)}
                          sx={{ ...linkButtonSx, color: "#64748B" }}
                        >
                          Release
                        </Button>
                      </Box>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableShell>
    </Box>
  );
}
