"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import type { PrecheckResult } from "@/lib/api/services/progression.service";
import {
  HeadRow,
  MUTED,
  Notice,
  StatTile,
  TableShell,
  bodyRowSx,
  cellSx,
  linkButtonSx,
  nameCellSx,
} from "../adminUi";
import { IssueList, PrecheckChip, SchoolDrawer, firstIssue } from "./shared";

export function StepPrecheck({ results }: { results: PrecheckResult[] }) {
  const [openId, setOpenId] = useState<number | null>(null);
  const open = results.find((r) => r.schoolId === openId) ?? null;
  const count = (status: string) => results.filter((r) => r.status === status).length;
  // Blocked first, then warnings, so the things to fix are on top.
  const order = { blocked: 0, warning: 1, ready: 2 } as const;
  const sorted = [...results].sort((a, b) => order[a.status] - order[b.status]);

  return (
    <Box>
      <Box sx={{ display: "flex", gap: 1.5, mb: 2 }}>
        <StatTile label="Ready" value={count("ready")} accent="#16A34A" />
        <StatTile label="Ready with warnings" value={count("warning")} accent="#B45309" />
        <StatTile label="Blocked" value={count("blocked")} accent="#DC2626" />
      </Box>
      {/* Plain-text summary kept for screen readers and tests. */}
      <Typography
        data-testid="precheck-summary"
        sx={{
          position: "absolute",
          width: 1,
          height: 1,
          overflow: "hidden",
          clip: "rect(0 0 0 0)",
        }}
      >
        {count("ready")} ready · {count("warning")} warning · {count("blocked")} blocked
      </Typography>

      {count("blocked") > 0 && (
        <Box sx={{ mb: 2 }}>
          <Notice tone="error">
            Blocked schools were removed from the selection. Fix the issue shown, then go Back and
            run the precheck again to include them.
          </Notice>
        </Box>
      )}

      <TableShell>
        <Table size="small">
          <TableHead>
            <HeadRow columns={["School", "Move", "Status", "Issues", ""]} />
          </TableHead>
          <TableBody>
            {sorted.map((r) => {
              const issue = firstIssue(r.blockers, r.warnings);
              return (
                <TableRow key={r.schoolId} sx={bodyRowSx}>
                  <TableCell sx={nameCellSx}>{r.schoolName}</TableCell>
                  <TableCell sx={{ ...cellSx, whiteSpace: "nowrap" }}>
                    {r.currentYearLabel ?? "—"} → {r.targetYearLabel ?? "—"}
                  </TableCell>
                  <TableCell sx={cellSx}>
                    <PrecheckChip status={r.status} />
                  </TableCell>
                  <TableCell sx={{ ...cellSx, fontSize: "12px", maxWidth: 460 }}>
                    {issue ?? <span style={{ color: MUTED }}>No issues</span>}
                  </TableCell>
                  <TableCell sx={cellSx} align="right">
                    <Button size="small" onClick={() => setOpenId(r.schoolId)} sx={linkButtonSx}>
                      Details
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableShell>

      <SchoolDrawer
        open={open !== null}
        title={open?.schoolName ?? ""}
        subtitle={
          open?.currentYearLabel
            ? `${open.currentYearLabel} → ${open.targetYearLabel ?? "—"}`
            : null
        }
        onClose={() => setOpenId(null)}
      >
        {open && (
          <>
            <Box>
              <PrecheckChip status={open.status} />
            </Box>
            <IssueList title="Blockers" issues={open.blockers} tone="error" />
            <IssueList title="Warnings" issues={open.warnings} />
            {open.blockers.length + open.warnings.length === 0 && (
              <Notice tone="success">No issues — ready to progress.</Notice>
            )}
          </>
        )}
      </SchoolDrawer>
    </Box>
  );
}
