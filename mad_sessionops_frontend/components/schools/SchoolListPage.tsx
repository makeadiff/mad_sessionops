"use client";

import { useState, useMemo, useEffect, useRef, useCallback } from "react";
import { useSelector } from "react-redux";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Skeleton from "@mui/material/Skeleton";
import { GraduationCap, Users, BookOpen } from "lucide-react";
import { colors } from "@/config/design-tokens";
import { SchoolToolbar } from "./SchoolToolbar";
import {
  exportAllChildren,
  exportAllVolunteers,
  exportGapReport,
  exportSchoolsSummary,
} from "@/lib/api/services/exports.service";
import { SchoolTable } from "./SchoolTable";
import { SchoolEmptyState } from "./SchoolEmptyState";
import { fetchSchools, parseSortOption } from "@/lib/api/services/schools.service";
import type {
  SchoolListItem,
  SchoolScopeWarning,
  SchoolSummary,
  SortOption,
} from "@/lib/api/services/schools.service";
import { selectScopeWarning } from "@/lib/redux/features/auth/authSlice";

interface SchoolListPageProps {
  userName: string;
}

// ── Metric card ───────────────────────────────────────────────────────────────

interface MetricCardProps {
  icon: React.ElementType;
  label: string;
  value: number | string;
  accent: string;
  loading: boolean;
}

function MetricCard({ icon: Icon, label, value, accent, loading }: MetricCardProps) {
  return (
    <Box
      sx={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        px: 2.5,
        py: 1.75,
        bgcolor: colors.white,
        border: `1px solid ${colors.gray[200]}`,
        borderRadius: "10px",
        minWidth: 0,
      }}
    >
      <Box
        sx={{
          width: 36,
          height: 36,
          borderRadius: "9px",
          bgcolor: `${accent}14`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <Icon size={17} strokeWidth={1.75} color={accent} />
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography
          sx={{
            fontSize: "10px",
            fontWeight: 600,
            color: colors.gray[400],
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            lineHeight: 1,
          }}
        >
          {label}
        </Typography>
        <Box sx={{ height: 26, display: "flex", alignItems: "center", mt: 0.375 }}>
          {loading ? (
            <Skeleton width={44} height={20} />
          ) : (
            <Typography
              sx={{ fontSize: "20px", fontWeight: 700, color: colors.gray[900], lineHeight: 1 }}
            >
              {typeof value === "number" ? value.toLocaleString() : value}
            </Typography>
          )}
        </Box>
      </Box>
    </Box>
  );
}

// ── Sort helpers ──────────────────────────────────────────────────────────────

const COLUMN_COMPARATORS: Record<
  NonNullable<ReturnType<typeof parseSortOption>["column"]>,
  (a: SchoolListItem, b: SchoolListItem) => number
> = {
  id: (a, b) => a.partnerId - b.partnerId,
  name: (a, b) => a.name.localeCompare(b.name),
  city: (a, b) => (a.city ?? "").localeCompare(b.city ?? ""),
  academicYear: (a, b) => (a.academicYearLabel ?? "").localeCompare(b.academicYearLabel ?? ""),
  classes: (a, b) => a.classesCount - b.classesCount,
  children: (a, b) => a.childrenCount - b.childrenCount,
  volunteers: (a, b) => a.volunteersCount - b.volunteersCount,
  assignments: (a, b) => a.assignmentsCount - b.assignmentsCount,
};

function sortSchools(schools: SchoolListItem[], sort: SortOption): SchoolListItem[] {
  const copy = [...schools];
  const { column, direction } = parseSortOption(sort);

  if (!column) {
    // "updated_desc" — no visible column, always most-recent first.
    return copy.sort((a, b) => {
      if (!a.updatedAt && !b.updatedAt) return 0;
      if (!a.updatedAt) return 1;
      if (!b.updatedAt) return -1;
      return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
    });
  }

  const compare = COLUMN_COMPARATORS[column];
  return copy.sort((a, b) => (direction === "asc" ? compare(a, b) : -compare(a, b)));
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function SchoolListPage({ userName }: SchoolListPageProps) {
  const loginScopeWarning = useSelector(selectScopeWarning);
  const [allSchools, setAllSchools] = useState<SchoolListItem[]>([]);
  const [summary, setSummary] = useState<SchoolSummary | null>(null);
  const [scopeWarning, setScopeWarning] = useState<SchoolScopeWarning | null>(
    loginScopeWarning ?? null
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [progressingCount, setProgressingCount] = useState(0);
  const [progressingDismissed, setProgressingDismissed] = useState(false);

  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [sort, setSort] = useState<SortOption>("updated_desc");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadSchools = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchSchools();
      setAllSchools(data.schools);
      setSummary(data.summary);
      setScopeWarning(data.scopeWarning);
      setProgressingCount(data.progressingCount ?? 0);
    } catch {
      setError("Could not load schools. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSchools();
  }, [loadSchools]);

  function handleSearchChange(v: string) {
    setSearch(v);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedSearch(v), 200);
  }

  function handleClearSearch() {
    setSearch("");
    setDebouncedSearch("");
  }

  const visibleSchools = useMemo(() => {
    let result = allSchools;
    if (debouncedSearch.trim()) {
      const q = debouncedSearch.toLowerCase();
      result = result.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          (s.city ?? "").toLowerCase().includes(q) ||
          (s.coName ?? "").toLowerCase().includes(q)
      );
    }
    return sortSchools(result, sort);
  }, [allSchools, debouncedSearch, sort]);

  const isEmpty = !loading && allSchools.length === 0;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#F8FAFC" }}>
      {/* ── Fixed top ─────────────────────────────────────────────────────────── */}
      <Box sx={{ flexShrink: 0, px: 4, pt: 3.5, pb: 2.5, bgcolor: "#F8FAFC" }}>
        {/* Title + subtitle */}
        <Box sx={{ mb: 2.5 }}>
          <Typography
            sx={{ fontSize: "24px", fontWeight: 700, color: colors.gray[900], lineHeight: 1.2 }}
          >
            My schools
          </Typography>
          <Box sx={{ mt: 0.5, height: 18, display: "flex", alignItems: "center" }}>
            {loading ? (
              <Skeleton width={180} height={13} />
            ) : summary ? (
              <Typography sx={{ fontSize: "13px", color: colors.gray[500] }}>
                {[
                  summary.academicYear ? `Academic year ${summary.academicYear}` : null,
                  (() => {
                    if (allSchools.length === 0) return null;
                    const cities = new Set(allSchools.map((s) => s.city).filter(Boolean));
                    if (cities.size === 0) return null;
                    return cities.size === 1 ? `${[...cities][0]}` : `${cities.size} cities`;
                  })(),
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </Typography>
            ) : null}
          </Box>
        </Box>

        {/* Metrics */}
        {!isEmpty && (
          <Box sx={{ display: "flex", gap: 1.5, mb: 2.5 }}>
            <MetricCard
              icon={BookOpen}
              label="Total schools"
              value={summary?.totalSchools ?? 0}
              accent="#0284C7"
              loading={loading}
            />
            <MetricCard
              icon={Users}
              label="Total children"
              value={summary?.childrenEnrolled ?? 0}
              accent="#7C3AED"
              loading={loading}
            />
            <MetricCard
              icon={GraduationCap}
              label="Total volunteers"
              value={summary?.activeVolunteers ?? 0}
              accent="#059669"
              loading={loading}
            />
          </Box>
        )}

        {/* Toolbar */}
        {!isEmpty && (
          <SchoolToolbar
            search={search}
            onSearchChange={handleSearchChange}
            sort={sort}
            onSortChange={setSort}
            exportOptions={[
              // F-M9-5: exports follow the applied (debounced) search, like the visible list
              { label: "Schools summary", onExport: () => exportSchoolsSummary(debouncedSearch) },
              { label: "All children", onExport: () => exportAllChildren(debouncedSearch) },
              { label: "All volunteers", onExport: () => exportAllVolunteers(debouncedSearch) },
              { label: "Gap report", onExport: () => exportGapReport(debouncedSearch) },
            ]}
          />
        )}

        {error && (
          <Typography sx={{ color: "error.main", mt: 1.5, fontSize: "13px" }}>{error}</Typography>
        )}

        {/* M10 F-M10-5: some of this user's schools are hidden while they progress */}
        {progressingCount > 0 && !progressingDismissed && (
          <Alert
            severity="info"
            onClose={() => setProgressingDismissed(true)}
            sx={{ mt: 1.5, fontSize: "13px" }}
          >
            {progressingCount === 1
              ? "1 of your schools is being moved to the next academic year. It will be back shortly."
              : `${progressingCount} of your schools are being moved to the next academic year. They will be back shortly.`}
          </Alert>
        )}
      </Box>

      {/* ── Table — fills remaining height ────────────────────────────────────── */}
      {isEmpty ? (
        <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          {scopeWarning ? (
            <Box
              sx={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                py: 8,
                px: 4,
                textAlign: "center",
              }}
            >
              <BookOpen size={32} color={colors.gray[400]} strokeWidth={1.5} />
              <Typography
                sx={{ mt: 2, mb: 1, fontWeight: 600, color: colors.gray[900], fontSize: "18px" }}
              >
                No schools assigned
              </Typography>
              <Typography sx={{ color: colors.gray[500], maxWidth: 380, lineHeight: 1.6 }}>
                {scopeWarning.message}
              </Typography>
            </Box>
          ) : (
            <SchoolEmptyState />
          )}
        </Box>
      ) : (
        <Box sx={{ flex: 1, overflow: "hidden", px: 4, pb: 3, minHeight: 0 }}>
          <SchoolTable
            schools={visibleSchools}
            loading={loading}
            searchQuery={debouncedSearch}
            onClearFilters={handleClearSearch}
            sort={sort}
            onSortChange={setSort}
          />
        </Box>
      )}
    </Box>
  );
}
