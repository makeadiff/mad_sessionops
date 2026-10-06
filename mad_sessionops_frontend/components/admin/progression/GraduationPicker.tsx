"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import Typography from "@mui/material/Typography";
import { fetchPreviewChildren, type PreviewChild } from "@/lib/api/services/progression.service";
import { showApiError } from "@/lib/toast/toast";
import { BORDER, MUTED, PanelHeading, SearchField, TEXT, linkButtonSx } from "../adminUi";

export interface ClassOption {
  classId: number;
  className: string;
}

/**
 * Graduation marks for one school: whole classes and/or individual children.
 * The server validates and counts them; this only collects ids.
 */
export function GraduationPicker({
  schoolId,
  classes,
  classIds,
  childIds,
  onChange,
}: {
  schoolId: number;
  classes: ClassOption[];
  classIds: number[];
  childIds: number[];
  onChange: (next: { classIds: number[]; childIds: number[] }) => void;
}) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [children, setChildren] = useState<PreviewChild[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setQuery(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    fetchPreviewChildren(schoolId, { search: query, page, pageSize: 50 })
      .then((res) => {
        if (cancelled) return;
        setTotal(res.total);
        setChildren((prev) => (page === 1 ? res.results : [...prev, ...res.results]));
      })
      .catch(showApiError)
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [schoolId, query, page]);

  const toggleClass = (id: number) =>
    onChange({
      classIds: classIds.includes(id) ? classIds.filter((c) => c !== id) : [...classIds, id],
      childIds,
    });
  const toggleChild = (id: number) =>
    onChange({
      classIds,
      childIds: childIds.includes(id) ? childIds.filter((c) => c !== id) : [...childIds, id],
    });

  const label = (text: string) => (
    <Typography sx={{ fontSize: "13px", color: TEXT }}>{text}</Typography>
  );

  return (
    <Box
      sx={{
        pt: 2,
        borderTop: `1px solid ${BORDER}`,
        display: "flex",
        flexDirection: "column",
        gap: 1.5,
      }}
    >
      <Box>
        <PanelHeading>Graduate (optional)</PanelHeading>
        <Typography sx={{ fontSize: "12px", color: MUTED, lineHeight: 1.5 }}>
          Marked children are deactivated with reason &quot;Graduated&quot;. Everyone else moves to
          their class&apos;s next class, or stays if it has none.
        </Typography>
      </Box>

      {classes.length > 0 && (
        <Box>
          <Typography sx={{ fontSize: "12px", fontWeight: 600, color: "#334155", mb: 0.25 }}>
            Whole classes
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", columnGap: 2 }}>
            {classes.map((c) => (
              <FormControlLabel
                key={c.classId}
                control={
                  <Checkbox
                    size="small"
                    checked={classIds.includes(c.classId)}
                    onChange={() => toggleClass(c.classId)}
                  />
                }
                label={label(`All of ${c.className}`)}
              />
            ))}
          </Box>
        </Box>
      )}

      <Box>
        <Typography sx={{ fontSize: "12px", fontWeight: 600, color: "#334155", mb: 0.75 }}>
          Individual children{childIds.length > 0 ? ` (${childIds.length} selected)` : ""}
        </Typography>
        <SearchField
          width="100%"
          placeholder="Search children by name"
          value={search}
          onChange={(v) => {
            setLoading(true);
            setPage(1);
            setSearch(v);
          }}
        />
        <Box
          sx={{
            maxHeight: 260,
            overflowY: "auto",
            mt: 1,
            border: `1px solid ${BORDER}`,
            borderRadius: "8px",
            px: 1,
            py: 0.5,
          }}
        >
          {children.map((ch) => (
            <FormControlLabel
              key={ch.childId}
              sx={{ display: "flex", mr: 0 }}
              control={
                <Checkbox
                  size="small"
                  checked={childIds.includes(ch.childId)}
                  onChange={() => toggleChild(ch.childId)}
                />
              }
              label={
                <Typography sx={{ fontSize: "13px", color: TEXT }}>
                  {ch.firstName} {ch.lastName}
                  <Typography component="span" sx={{ fontSize: "12px", color: MUTED }}>
                    {" "}
                    · {ch.className ?? "No class"}
                    {ch.sectionName ? ` · ${ch.sectionName}` : ""}
                  </Typography>
                </Typography>
              }
            />
          ))}
          {!loading && children.length === 0 && (
            <Typography sx={{ fontSize: "12px", color: MUTED, py: 1.5, textAlign: "center" }}>
              No children found.
            </Typography>
          )}
          {loading && (
            <Box sx={{ display: "flex", justifyContent: "center", py: 1 }}>
              <CircularProgress size={16} sx={{ color: "#2563EB" }} />
            </Box>
          )}
        </Box>
        {children.length < total && !loading && (
          <Button
            size="small"
            sx={{ ...linkButtonSx, mt: 0.5 }}
            onClick={() => {
              setLoading(true);
              setPage((p) => p + 1);
            }}
          >
            Load more ({total - children.length} left)
          </Button>
        )}
      </Box>
    </Box>
  );
}
