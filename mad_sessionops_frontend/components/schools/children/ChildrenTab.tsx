"use client";

import { useState, useEffect, useCallback } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import InputAdornment from "@mui/material/InputAdornment";
import IconButton from "@mui/material/IconButton";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import { Plus, Search, X, User, Pencil, UserMinus, UserCheck, BookOpen, Heart } from "lucide-react";
import {
  fetchChildren,
  type ChildItem,
  type ListChildrenParams,
} from "@/lib/api/services/children.service";
import { fetchSchoolClasses, type SchoolClassItem } from "@/lib/api/services/structure.service";
import { fetchBuckets, type BucketItem } from "@/lib/api/services/buckets.service";
import { EnrollChildModal } from "./EnrollChildModal";
import { EditChildDrawer } from "./EditChildDrawer";
import { DeactivateChildModal } from "./DeactivateChildModal";
import { ReactivateChildModal } from "./ReactivateChildModal";
import { RichEmptyState } from "@/components/schools/shared/RichEmptyState";
import { ExportButton } from "@/components/ui/ExportButton";
import { exportSchoolChildren } from "@/lib/api/services/exports.service";
import toast from "react-hot-toast";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ChildrenTabProps {
  schoolId: number;
  activeYear: string;
  canModify?: boolean;
}

type StatusFilter = "active" | "inactive" | "all";

// ── Design tokens ─────────────────────────────────────────────────────────────

const BORDER = "#E2E8F0";
const TH_BG = "#F8FAFC";
const TH_TEXT = "#64748B";
const ROW_HOVER = "#F8FAFC";
const MUTED = "#94A3B8";
const TEXT = "#1E293B";

// ── Helpers ───────────────────────────────────────────────────────────────────

function genderColor(g: string): string {
  if (g === "female") return "#DB2777";
  if (g === "male") return "#2563EB";
  return "#7C3AED";
}

// ── Status pill tabs ──────────────────────────────────────────────────────────

const STATUS_OPTS: { value: StatusFilter; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "all", label: "All" },
];

interface StatusTabsProps {
  value: StatusFilter;
  counts: Record<StatusFilter, number | null>;
  onChange: (v: StatusFilter) => void;
}

function StatusTabs({ value, counts, onChange }: StatusTabsProps) {
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        bgcolor: "#FAFAFA",
        borderRadius: "8px",
        border: `1px solid ${BORDER}`,
        p: 0.5,
        gap: 0.25,
      }}
    >
      {STATUS_OPTS.map((opt) => {
        const active = value === opt.value;
        const count = counts[opt.value];
        return (
          <Box
            key={opt.value}
            onClick={() => onChange(opt.value)}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 0.75,
              px: 1.25,
              py: 0.75,
              borderRadius: "6px",
              cursor: "pointer",
              transition: "all 0.12s ease",
              bgcolor: active ? "#fff" : "transparent",
              boxShadow: active ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
              "&:hover": { bgcolor: active ? "#fff" : "#EFF6FF" },
            }}
          >
            <Typography
              sx={{
                fontSize: "12px",
                fontWeight: active ? 600 : 500,
                color: active ? "#0F172A" : TH_TEXT,
                lineHeight: 1,
              }}
            >
              {opt.label}
            </Typography>
            {count !== null && (
              <Box
                sx={{
                  minWidth: 18,
                  height: 18,
                  px: 0.75,
                  borderRadius: "5px",
                  bgcolor: active ? "#2563EB" : "#E2E8F0",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Typography
                  sx={{
                    fontSize: "10px",
                    fontWeight: 700,
                    color: active ? "#fff" : TH_TEXT,
                    lineHeight: 1,
                  }}
                >
                  {count}
                </Typography>
              </Box>
            )}
          </Box>
        );
      })}
    </Box>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ onEnroll }: { onEnroll?: () => void }) {
  return (
    <RichEmptyState
      badgeIcon={User}
      badgeText="Get started"
      heading="Add children to start your school's journey"
      subtitle={
        onEnroll
          ? "Enroll the first child to start tracking their class, mentoring circle, and attendance right here on Session-Ops."
          : "No children have been enrolled in this school yet."
      }
      bullets={
        onEnroll
          ? [
              { icon: BookOpen, text: "Enroll children into classes and mentoring circles" },
              { icon: UserCheck, text: "Track attendance and progress through the year" },
              {
                icon: Heart,
                text: "Every child enrolled is a step closer to the difference you're making",
              },
            ]
          : undefined
      }
      ctaLabel={onEnroll ? "Enroll Child" : undefined}
      onCta={onEnroll}
      accent="#2563EB"
    />
  );
}

// ── No results ────────────────────────────────────────────────────────────────

function NoResults({ onClear }: { onClear: () => void }) {
  return (
    <Box sx={{ mt: 8, display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
      <Typography sx={{ fontSize: "14px", fontWeight: 500, color: "#475569" }}>
        No children match the selected filters.
      </Typography>
      <Button
        size="small"
        variant="text"
        onClick={onClear}
        sx={{ fontSize: "12px", color: "#2563EB", textTransform: "none" }}
      >
        Clear filters
      </Button>
    </Box>
  );
}

// ── Skeleton rows ─────────────────────────────────────────────────────────────

function SkeletonRows() {
  return (
    <>
      {[1, 2, 3, 4, 5].map((i) => (
        <TableRow key={i}>
          <TableCell sx={{ py: 1.5 }}>
            <Skeleton variant="text" width={16} height={14} />
          </TableCell>
          <TableCell sx={{ py: 1.5 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
              <Skeleton variant="circular" width={32} height={32} />
              <Box>
                <Skeleton variant="text" width={120} height={14} />
                <Skeleton variant="text" width={70} height={12} sx={{ mt: 0.25 }} />
              </Box>
            </Box>
          </TableCell>
          {[50, 40, 90, 100, 60, 20].map((w, j) => (
            <TableCell key={j} sx={{ py: 1.5 }}>
              <Skeleton variant="text" width={w} height={14} />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

// ── Child row ─────────────────────────────────────────────────────────────────

const GENDER_LABELS: Record<string, string> = { male: "Male", female: "Female", other: "Other" };

function ChildRow({
  child,
  index,
  onEdit,
  onDeactivate,
  onReactivate,
}: {
  child: ChildItem;
  index: number;
  onEdit: (c: ChildItem) => void;
  onDeactivate: (c: ChildItem) => void;
  onReactivate: (c: ChildItem) => void;
}) {
  const gc = genderColor(child.gender);
  return (
    <TableRow sx={{ "&:hover": { bgcolor: ROW_HOVER } }}>
      {/* Serial number */}
      <TableCell sx={{ py: 1.25 }}>
        <Typography sx={{ fontSize: "13px", color: MUTED }}>{index}</Typography>
      </TableCell>

      {/* Name cell */}
      <TableCell sx={{ py: 1.25 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <Box
            sx={{
              width: 32,
              height: 32,
              borderRadius: "50%",
              bgcolor: `${gc}18`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <Typography sx={{ fontSize: "11px", fontWeight: 700, color: gc }}>
              {child.firstName[0]}
              {child.lastName[0]}
            </Typography>
          </Box>
          <Box>
            <Typography sx={{ fontSize: "13px", fontWeight: 500, color: TEXT, lineHeight: 1.3 }}>
              {child.firstName} {child.lastName}
            </Typography>
            {child.city && (
              <Typography sx={{ fontSize: "11px", color: MUTED, lineHeight: 1.3 }}>
                {child.city}
              </Typography>
            )}
          </Box>
        </Box>
      </TableCell>

      {/* Gender */}
      <TableCell sx={{ py: 1.25 }}>
        <Box
          sx={{
            display: "inline-flex",
            alignItems: "center",
            gap: 0.5,
            px: 0.875,
            py: 0.25,
            borderRadius: "4px",
            bgcolor: `${gc}14`,
          }}
        >
          <Typography sx={{ fontSize: "11px", fontWeight: 600, color: gc }}>
            {GENDER_LABELS[child.gender] ?? child.gender}
          </Typography>
        </Box>
      </TableCell>

      {/* Age */}
      <TableCell sx={{ py: 1.25 }}>
        <Typography sx={{ fontSize: "13px", color: "#475569" }}>{child.age ?? "—"}</Typography>
      </TableCell>

      {/* Class */}
      <TableCell sx={{ py: 1.25 }}>
        <Typography sx={{ fontSize: "13px", color: "#475569" }}>
          {child.currentSchoolClass?.className || "—"}
        </Typography>
      </TableCell>

      {/* Bucket */}
      <TableCell sx={{ py: 1.25 }}>
        {child.currentSection ? (
          <Typography sx={{ fontSize: "13px", color: "#475569" }}>
            {child.currentSection.sectionDisplayName ?? child.currentSection.sectionName}
          </Typography>
        ) : (
          <Chip
            label="Unassigned"
            size="small"
            sx={{
              fontSize: "11px",
              fontWeight: 600,
              height: 20,
              borderRadius: "4px",
              bgcolor: "#F1F5F9",
              color: "#64748B",
            }}
          />
        )}
      </TableCell>

      {/* Status */}
      <TableCell sx={{ py: 1.25 }}>
        <Chip
          label={child.isActive ? "Active" : "Inactive"}
          size="small"
          sx={{
            fontSize: "11px",
            fontWeight: 600,
            height: 20,
            borderRadius: "4px",
            bgcolor: child.isActive ? "#DCFCE7" : "#FEE2E2",
            color: child.isActive ? "#16A34A" : "#DC2626",
          }}
        />
      </TableCell>

      {/* Actions */}
      <TableCell sx={{ py: 1.25 }}>
        <Box sx={{ display: "flex", gap: 0.5 }}>
          <IconButton
            size="small"
            onClick={() => onEdit(child)}
            sx={{ color: MUTED, "&:hover": { color: "#2563EB", bgcolor: "#EFF6FF" } }}
          >
            <Pencil size={13} />
          </IconButton>
          {child.isActive && (
            <IconButton
              size="small"
              onClick={() => onDeactivate(child)}
              sx={{ color: MUTED, "&:hover": { color: "#DC2626", bgcolor: "#FEF2F2" } }}
            >
              <UserMinus size={13} />
            </IconButton>
          )}
          {!child.isActive && (
            <IconButton
              size="small"
              onClick={() => onReactivate(child)}
              sx={{ color: MUTED, "&:hover": { color: "#16A34A", bgcolor: "#F0FDF4" } }}
            >
              <UserCheck size={13} />
            </IconButton>
          )}
        </Box>
      </TableCell>
    </TableRow>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function ChildrenTab({ schoolId, activeYear, canModify = true }: ChildrenTabProps) {
  const [allChildren, setAllChildren] = useState<ChildItem[]>([]);
  const [allActive, setAllActive] = useState<number | null>(null);
  const [allInactive, setAllInactive] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebounced] = useState("");
  const [status, setStatus] = useState<StatusFilter>("active");
  const [classId, setClassId] = useState<number | null>(null);
  const [bucketFilter, setBucketFilter] = useState<"all" | "unassigned" | number>("all");
  const [classes, setClasses] = useState<SchoolClassItem[]>([]);
  const [buckets, setBuckets] = useState<BucketItem[]>([]);
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [editChild, setEditChild] = useState<ChildItem | null>(null);
  const [deactivateChild, setDeactivateChild] = useState<ChildItem | null>(null);
  const [reactivateChild, setReactivateChild] = useState<ChildItem | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  function handleClassChange(id: number | null) {
    setClassId(id);
  }

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  // Load school classes once for the filter dropdown
  useEffect(() => {
    fetchSchoolClasses(schoolId)
      .then(setClasses)
      .catch(() => {});
  }, [schoolId]);

  // Load buckets once for the filter dropdown — independent of class (buckets are class-agnostic)
  useEffect(() => {
    fetchBuckets(schoolId)
      .then(setBuckets)
      .catch(() => {});
  }, [schoolId]);

  // Main data load — status='all' so status tab changes are instant (client-side)
  // class_id/section_id/unassigned are sent to the API since inactive children have no active assignment
  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setLoadError(false);
      try {
        const params: ListChildrenParams = { status: "all" };
        if (debouncedSearch) params.search = debouncedSearch;
        if (classId) params.class_id = classId;
        if (bucketFilter === "unassigned") params.unassigned = true;
        else if (bucketFilter !== "all") params.section_id = bucketFilter;
        const data = await fetchChildren(schoolId, params);
        if (cancelled) return;
        setAllChildren(data);
        setAllActive(data.filter((c) => c.isActive).length);
        setAllInactive(data.filter((c) => !c.isActive).length);
      } catch {
        if (cancelled) return;
        setLoadError(true);
        toast.error("Could not load children");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [schoolId, debouncedSearch, classId, bucketFilter, refreshKey]);

  // Derived — status tab changes are instant (client-side)
  const displayChildren =
    status === "active"
      ? allChildren.filter((c) => c.isActive)
      : status === "inactive"
        ? allChildren.filter((c) => !c.isActive)
        : allChildren;

  const totalActive = allActive ?? 0;
  const totalInactive = allInactive ?? 0;

  const counts: Record<StatusFilter, number | null> = {
    active: loading ? null : totalActive,
    inactive: loading ? null : totalInactive,
    all: loading ? null : totalActive + totalInactive,
  };

  const hasFilters = !!debouncedSearch || !!classId || bucketFilter !== "all";

  // F-M9-2: export exactly the current view — same filters as the list request, plus status.
  const handleExport = () =>
    exportSchoolChildren(schoolId, {
      status,
      search: debouncedSearch,
      classId,
      sectionId: typeof bucketFilter === "number" ? bucketFilter : null,
      unassigned: bucketFilter === "unassigned",
    });
  const isEmpty = !loading && !loadError && allChildren.length === 0 && !hasFilters;
  const noResults = !loading && !loadError && displayChildren.length === 0 && !isEmpty;

  return (
    <>
      <Box sx={{ px: 4, pt: 3, pb: 6 }}>
        {/* ── Page header ── */}
        <Box
          sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", mb: 3 }}
        >
          <Box>
            <Typography sx={{ fontSize: "18px", fontWeight: 700, color: "#0F172A" }}>
              Children
            </Typography>
            {activeYear && (
              <Typography sx={{ fontSize: "12px", color: MUTED, mt: 0.25 }}>
                Academic Year: {activeYear}
              </Typography>
            )}
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <ExportButton
              disabled={loading || loadError}
              options={[{ label: "Children", onExport: handleExport }]}
            />
            {canModify && (
              <Button
                variant="contained"
                size="small"
                startIcon={<Plus size={14} />}
                onClick={() => setEnrollOpen(true)}
                sx={{
                  bgcolor: "#2563EB",
                  "&:hover": { bgcolor: "#1D4ED8" },
                  fontSize: "13px",
                  fontWeight: 600,
                  boxShadow: "none",
                }}
              >
                Enroll Child
              </Button>
            )}
          </Box>
        </Box>

        {/* ── Toolbar: search + class/section + status ── */}
        {!isEmpty && !loadError && (
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1.5,
              mb: 2.5,
              flexWrap: "wrap",
            }}
          >
            {/* Search */}
            <TextField
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name…"
              size="small"
              sx={{
                width: 220,
                "& .MuiOutlinedInput-root": {
                  fontSize: "13px",
                  borderRadius: "8px",
                  bgcolor: "#FAFAFA",
                  "& fieldset": { borderColor: BORDER },
                  "&:hover fieldset": { borderColor: "#CBD5E1" },
                  "&.Mui-focused fieldset": { borderColor: "#2563EB", borderWidth: "1.5px" },
                },
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search size={13} color={MUTED} />
                  </InputAdornment>
                ),
                endAdornment: search ? (
                  <InputAdornment position="end">
                    <IconButton
                      size="small"
                      onClick={() => setSearch("")}
                      edge="end"
                      sx={{ p: 0.25 }}
                    >
                      <X size={13} color={MUTED} />
                    </IconButton>
                  </InputAdornment>
                ) : undefined,
              }}
            />

            {/* Class filter */}
            {classes.length > 0 && (
              <FormControl size="small">
                <Select
                  value={classId ?? ""}
                  onChange={(e) =>
                    handleClassChange(e.target.value ? Number(e.target.value) : null)
                  }
                  displayEmpty
                  sx={{
                    fontSize: "13px",
                    borderRadius: "8px",
                    minWidth: 120,
                    bgcolor: "#FAFAFA",
                    "& .MuiOutlinedInput-notchedOutline": { borderColor: BORDER },
                    "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: "#CBD5E1" },
                    "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
                      borderColor: "#2563EB",
                      borderWidth: "1.5px",
                    },
                    "& .MuiSelect-select": { py: "6.5px" },
                  }}
                >
                  <MenuItem value="">
                    <Typography sx={{ fontSize: "13px", color: MUTED }}>All classes</Typography>
                  </MenuItem>
                  {classes.map((c) => (
                    <MenuItem key={c.schoolClassId} value={c.schoolClassId}>
                      <Typography sx={{ fontSize: "13px" }}>{c.className}</Typography>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}

            {/* Bucket filter — independent of class (buckets are class-agnostic) */}
            {buckets.length > 0 && (
              <FormControl size="small">
                <Select
                  value={bucketFilter}
                  onChange={(e) =>
                    setBucketFilter(
                      e.target.value === "all" || e.target.value === "unassigned"
                        ? e.target.value
                        : Number(e.target.value)
                    )
                  }
                  displayEmpty
                  sx={{
                    fontSize: "13px",
                    borderRadius: "8px",
                    minWidth: 130,
                    bgcolor: "#FAFAFA",
                    "& .MuiOutlinedInput-notchedOutline": { borderColor: BORDER },
                    "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: "#CBD5E1" },
                    "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
                      borderColor: "#2563EB",
                      borderWidth: "1.5px",
                    },
                    "& .MuiSelect-select": { py: "6.5px" },
                  }}
                >
                  <MenuItem value="all">
                    <Typography sx={{ fontSize: "13px", color: MUTED }}>
                      All mentoring circles
                    </Typography>
                  </MenuItem>
                  <MenuItem value="unassigned">
                    <Typography sx={{ fontSize: "13px" }}>Unassigned</Typography>
                  </MenuItem>
                  {buckets.map((b) => (
                    <MenuItem key={b.classSectionId} value={b.classSectionId}>
                      <Typography sx={{ fontSize: "13px" }}>
                        {b.sectionDisplayName ?? b.sectionName}
                      </Typography>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}

            {/* Status pill tabs */}
            <StatusTabs value={status} counts={counts} onChange={setStatus} />

            {/* Result count — far right */}
            {!loading && (
              <Typography sx={{ fontSize: "12px", color: MUTED, ml: "auto" }}>
                {displayChildren.length} {displayChildren.length === 1 ? "result" : "results"}
              </Typography>
            )}
          </Box>
        )}

        {/* ── Load error ── */}
        {loadError && (
          <Box
            sx={{ mt: 8, display: "flex", flexDirection: "column", alignItems: "center", gap: 1.5 }}
          >
            <Typography sx={{ fontSize: "14px", color: "#EF4444" }}>
              Failed to load children.
            </Typography>
            <Button variant="outlined" size="small" onClick={refresh} sx={{ fontSize: "13px" }}>
              Retry
            </Button>
          </Box>
        )}

        {/* ── States ── */}
        {isEmpty && <EmptyState onEnroll={canModify ? () => setEnrollOpen(true) : undefined} />}
        {noResults && (
          <NoResults
            onClear={() => {
              setSearch("");
              handleClassChange(null);
              setBucketFilter("all");
            }}
          />
        )}

        {/* ── Table ── */}
        {!isEmpty && !noResults && !loadError && (
          <TableContainer
            sx={{
              border: `1px solid ${BORDER}`,
              borderRadius: "10px",
              overflow: "hidden",
            }}
          >
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: TH_BG }}>
                  {["#", "Name", "Gender", "Age", "Class", "Mentoring Circle", "Status", ""].map(
                    (h) => (
                      <TableCell
                        key={h}
                        sx={{
                          fontSize: "11px",
                          fontWeight: 600,
                          color: TH_TEXT,
                          textTransform: "uppercase",
                          letterSpacing: "0.05em",
                          py: 1.25,
                          borderBottom: `1px solid ${BORDER}`,
                        }}
                      >
                        {h}
                      </TableCell>
                    )
                  )}
                </TableRow>
              </TableHead>
              <TableBody>
                {loading ? (
                  <SkeletonRows />
                ) : (
                  displayChildren.map((c, i) => (
                    <ChildRow
                      key={c.childId}
                      child={c}
                      index={i + 1}
                      onEdit={setEditChild}
                      onDeactivate={setDeactivateChild}
                      onReactivate={setReactivateChild}
                    />
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Box>

      <EnrollChildModal
        open={enrollOpen}
        schoolId={schoolId}
        onClose={() => setEnrollOpen(false)}
        onSuccess={refresh}
      />

      {editChild && (
        <EditChildDrawer
          open={editChild !== null}
          schoolId={schoolId}
          child={editChild}
          onClose={() => setEditChild(null)}
          onSuccess={refresh}
        />
      )}

      {deactivateChild && (
        <DeactivateChildModal
          open={deactivateChild !== null}
          schoolId={schoolId}
          child={deactivateChild}
          onClose={() => setDeactivateChild(null)}
          onSuccess={refresh}
        />
      )}

      {reactivateChild && (
        <ReactivateChildModal
          open={reactivateChild !== null}
          schoolId={schoolId}
          child={reactivateChild}
          onClose={() => setReactivateChild(null)}
          onSuccess={refresh}
        />
      )}
    </>
  );
}

export default ChildrenTab;
