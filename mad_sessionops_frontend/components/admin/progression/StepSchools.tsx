"use client";

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Radio from "@mui/material/Radio";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import type { EligibleSchool } from "@/lib/api/services/progression.service";
import {
  EmptyRow,
  HeadRow,
  MUTED,
  Pill,
  SearchField,
  SegmentedTabs,
  TableShell,
  bodyRowSx,
  cellSx,
  nameCellSx,
} from "../adminUi";

type Filter = "eligible" | "all";

export function StepSchools({
  schools,
  selected,
  onChange,
}: {
  schools: EligibleSchool[];
  selected: Set<number>;
  onChange: (next: Set<number>) => void;
}) {
  const [search, setSearch] = useState("");
  const eligibleCount = schools.filter((s) => s.eligible).length;
  // Show only the schools that can move unless the admin asks to see everything.
  const [filter, setFilter] = useState<Filter>(eligibleCount > 0 ? "eligible" : "all");
  // Schools can be on different years; filter by the year they are on now.
  const years = useMemo(
    () =>
      [...new Set(schools.map((s) => s.currentYearLabel).filter((y): y is string => !!y))].sort(),
    [schools]
  );
  const [year, setYear] = useState<string>("all");

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return schools
      .filter((s) => filter === "all" || s.eligible)
      .filter((s) => year === "all" || s.currentYearLabel === year)
      .filter(
        (s) =>
          !q || s.schoolName.toLowerCase().includes(q) || (s.city ?? "").toLowerCase().includes(q)
      )
      .sort((a, b) => Number(b.eligible) - Number(a.eligible));
  }, [schools, search, filter, year]);
  // One school per run: picking a school replaces the previous choice.
  const choose = (id: number) => onChange(new Set([id]));

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 2, flexWrap: "wrap" }}>
        <SearchField value={search} onChange={setSearch} placeholder="Search schools or cities" />
        <SegmentedTabs
          ariaLabel="Filter schools"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "eligible", label: "Can move", count: eligibleCount },
            { value: "all", label: "All converted", count: schools.length },
          ]}
        />
        {years.length > 1 && (
          <SegmentedTabs
            ariaLabel="Filter by current year"
            value={year}
            onChange={setYear}
            options={[
              { value: "all", label: "All years" },
              ...years.map((y) => ({
                value: y,
                label: y,
                count: schools.filter((s) => s.currentYearLabel === y).length,
              })),
            ]}
          />
        )}
      </Box>

      <TableShell>
        <Table size="small">
          <TableHead>
            <HeadRow
              columns={[
                { width: 48, label: "" },
                "School",
                "City",
                "Current year",
                "Moves to",
                "Status",
              ]}
            />
          </TableHead>
          <TableBody>
            {visible.length === 0 ? (
              <EmptyRow
                cols={6}
                message={
                  search ? "No schools match your search." : "No schools can move right now."
                }
              />
            ) : (
              visible.map((s) => (
                <TableRow
                  key={s.schoolId}
                  data-testid={`school-row-${s.schoolId}`}
                  onClick={s.eligible ? () => choose(s.schoolId) : undefined}
                  sx={{
                    ...bodyRowSx,
                    cursor: s.eligible ? "pointer" : "default",
                    bgcolor: selected.has(s.schoolId) ? "#F0F7FF" : undefined,
                  }}
                >
                  <TableCell padding="checkbox" sx={{ ...cellSx, py: 0 }}>
                    <Radio
                      size="small"
                      name="progression-school"
                      checked={selected.has(s.schoolId)}
                      disabled={!s.eligible}
                      onClick={(e) => e.stopPropagation()}
                      onChange={() => choose(s.schoolId)}
                      slotProps={{ input: { "aria-label": `Select ${s.schoolName}` } }}
                    />
                  </TableCell>
                  <TableCell sx={{ ...nameCellSx, color: s.eligible ? nameCellSx.color : MUTED }}>
                    {s.schoolName}
                  </TableCell>
                  <TableCell sx={cellSx}>{s.city ?? "—"}</TableCell>
                  <TableCell sx={cellSx}>
                    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
                      {s.currentYearLabel ?? "—"}
                      {s.yearsBehind > 0 && (
                        <Pill
                          label={`${s.yearsBehind} yr behind`}
                          tone={s.yearsBehind > 1 ? "warning" : "neutral"}
                        />
                      )}
                    </Box>
                  </TableCell>
                  <TableCell sx={cellSx}>{s.targetYearLabel ?? "—"}</TableCell>
                  <TableCell sx={cellSx}>
                    {s.eligible ? (
                      <Pill label="Can move" tone="success" />
                    ) : (
                      <Typography component="span" sx={{ fontSize: "12px", color: MUTED }}>
                        {s.reasonMessage ?? "Not eligible"}
                      </Typography>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableShell>
    </Box>
  );
}
