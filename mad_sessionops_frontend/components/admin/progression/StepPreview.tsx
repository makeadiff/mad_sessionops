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
import type { PreviewResult } from "@/lib/api/services/progression.service";
import {
  HeadRow,
  KeyValue,
  MUTED,
  PanelHeading,
  StatTile,
  TableShell,
  bodyRowSx,
  cellSx,
  linkButtonSx,
  nameCellSx,
} from "../adminUi";
import { GraduationPicker, type ClassOption } from "./GraduationPicker";
import { IssueList, SchoolDrawer } from "./shared";

export type MarksBySchool = Record<number, { classIds: number[]; childIds: number[] }>;

function sum(rows: { n: number }[]) {
  return rows.reduce((t, r) => t + r.n, 0);
}

function archivedTotal(r: PreviewResult) {
  return Object.values(r.counts.archiveCounts).reduce((t, n) => t + n, 0);
}

/** Class names present in the school's plan, mapped to catalog ids for graduation. */
function classOptions(r: PreviewResult, idByName: Record<string, number>): ClassOption[] {
  const names = new Set<string>([
    ...r.counts.childrenMoving.map((m) => m.from),
    ...r.counts.childrenStaying.map((s) => s.class),
  ]);
  return [...names]
    .filter((n) => idByName[n] !== undefined)
    .map((n) => ({ classId: idByName[n], className: n }));
}

const COLUMNS = [
  "School",
  "Move",
  { label: "Classes", align: "right" as const },
  { label: "Sections", align: "right" as const },
  { label: "Moving up", align: "right" as const },
  { label: "Staying", align: "right" as const },
  { label: "Graduating", align: "right" as const },
  { label: "Volunteers", align: "right" as const },
  { label: "Archived", align: "right" as const },
  "",
];

export function StepPreview({
  results,
  marks,
  classIdByName,
  onMarksChange,
}: {
  results: PreviewResult[];
  marks: MarksBySchool;
  classIdByName: Record<string, number>;
  onMarksChange: (schoolId: number, next: { classIds: number[]; childIds: number[] }) => void;
}) {
  const [openId, setOpenId] = useState<number | null>(null);
  const open = results.find((r) => r.schoolId === openId) ?? null;

  const total = (fn: (r: PreviewResult) => number) => results.reduce((t, r) => t + fn(r), 0);

  return (
    <Box>
      <Box sx={{ display: "flex", gap: 1.5, mb: 2, flexWrap: "wrap" }}>
        <StatTile
          label="Children moving up"
          value={total((r) => sum(r.counts.childrenMoving))}
          accent="#2563EB"
        />
        <StatTile label="Staying in class" value={total((r) => sum(r.counts.childrenStaying))} />
        <StatTile
          label="Graduating"
          value={total((r) => r.counts.childrenGraduating)}
          accent="#7C3AED"
        />
        <StatTile label="Sections copied" value={total((r) => r.counts.sectionsCopied)} />
        <StatTile label="Rows archived" value={total(archivedTotal)} accent="#B45309" />
      </Box>
      <Typography sx={{ fontSize: "12px", color: MUTED, mb: 1.25 }}>
        Open a school to see its class moves or mark children as graduated.
      </Typography>

      <TableShell>
        <Table size="small">
          <TableHead>
            <HeadRow columns={COLUMNS} />
          </TableHead>
          <TableBody>
            {results.map((r) => (
              <TableRow key={r.schoolId} sx={bodyRowSx} data-testid={`preview-row-${r.schoolId}`}>
                <TableCell sx={nameCellSx}>{r.schoolName}</TableCell>
                <TableCell sx={{ ...cellSx, whiteSpace: "nowrap" }}>
                  {r.currentYearLabel ?? "—"} → {r.targetYearLabel ?? "—"}
                </TableCell>
                <TableCell sx={cellSx} align="right">
                  {r.counts.schoolClassesCopied + r.counts.schoolClassesAdded.length}
                </TableCell>
                <TableCell sx={cellSx} align="right">
                  {r.counts.sectionsCopied}
                </TableCell>
                <TableCell sx={cellSx} align="right">
                  {sum(r.counts.childrenMoving)}
                </TableCell>
                <TableCell sx={cellSx} align="right">
                  {sum(r.counts.childrenStaying)}
                </TableCell>
                <TableCell
                  sx={{
                    ...cellSx,
                    fontWeight: r.counts.childrenGraduating ? 600 : 400,
                    color: r.counts.childrenGraduating ? "#7C3AED" : cellSx.color,
                  }}
                  align="right"
                >
                  {r.counts.childrenGraduating}
                </TableCell>
                <TableCell sx={cellSx} align="right">
                  {r.counts.volunteersCarried}
                </TableCell>
                <TableCell sx={cellSx} align="right">
                  {archivedTotal(r)}
                </TableCell>
                <TableCell sx={cellSx} align="right">
                  <Button size="small" onClick={() => setOpenId(r.schoolId)} sx={linkButtonSx}>
                    Details
                  </Button>
                </TableCell>
              </TableRow>
            ))}
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
              <PanelHeading>Class moves</PanelHeading>
              {open.counts.childrenMoving.map((m) => (
                <KeyValue key={`${m.from}-${m.to}`} label={`${m.from} → ${m.to}`} value={m.n} />
              ))}
              {open.counts.childrenStaying.map((s) => (
                <KeyValue key={s.class} label={`${s.class} (stays)`} value={s.n} />
              ))}
              {open.counts.childrenMoving.length + open.counts.childrenStaying.length === 0 && (
                <Typography sx={{ fontSize: "13px", color: MUTED }}>
                  No children to move.
                </Typography>
              )}
              {open.counts.schoolClassesAdded.length > 0 && (
                <Typography sx={{ fontSize: "12px", color: MUTED, mt: 1 }}>
                  Classes added to the school: {open.counts.schoolClassesAdded.join(", ")}
                </Typography>
              )}
            </Box>
            <IssueList title="Warnings" issues={open.warnings} />
            <GraduationPicker
              schoolId={open.schoolId}
              classes={classOptions(open, classIdByName)}
              classIds={marks[open.schoolId]?.classIds ?? []}
              childIds={marks[open.schoolId]?.childIds ?? []}
              onChange={(next) => onMarksChange(open.schoolId, next)}
            />
          </>
        )}
      </SchoolDrawer>
    </Box>
  );
}
