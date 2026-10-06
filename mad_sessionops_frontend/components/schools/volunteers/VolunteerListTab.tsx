"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Skeleton from "@mui/material/Skeleton";
import { UserCheck, AlertCircle, Building2, Clock, Heart } from "lucide-react";
import {
  fetchVolunteers,
  type VolunteerListResponse,
  type VolunteerCard as VolunteerCardType,
} from "@/lib/api/services/volunteers.service";
import { VolunteerCard } from "./VolunteerCard";
import { VolunteerDetailDrawer } from "./VolunteerDetailDrawer";
import { RichEmptyState } from "@/components/schools/shared/RichEmptyState";
import { ExportButton } from "@/components/ui/ExportButton";
import { exportSchoolVolunteers } from "@/lib/api/services/exports.service";

// ── Design tokens ──────────────────────────────────────────────────────────────

const TEXT = "#1E293B";
const MUTED = "#64748B";
const SUBTLE = "#94A3B8";
const BORDER = "#E2E8F0";

// ── Skeleton ──────────────────────────────────────────────────────────────────

function VolunteerSkeleton() {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, px: 4, pt: 3, pb: 4 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 2 }}>
        <Skeleton width={140} height={14} />
      </Box>
      {[1, 2, 3].map((i) => (
        <Box
          key={i}
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 2,
            px: 2.5,
            py: 1.75,
            borderRadius: "10px",
            border: `1px solid ${BORDER}`,
            bgcolor: "#fff",
          }}
        >
          <Skeleton variant="circular" width={36} height={36} />
          <Box sx={{ flex: 1 }}>
            <Skeleton width="40%" height={14} sx={{ mb: 0.5 }} />
            <Skeleton width="60%" height={12} />
          </Box>
          <Skeleton width={80} height={24} sx={{ borderRadius: "6px" }} />
          <Skeleton width={70} height={24} sx={{ borderRadius: "6px" }} />
        </Box>
      ))}
    </Box>
  );
}

// ── Empty / Error states ──────────────────────────────────────────────────────

function InfoState({
  icon: Icon,
  title,
  subtitle,
}: {
  icon: React.ElementType;
  title: string;
  subtitle: string;
}) {
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: 280,
        gap: 1.5,
        px: 4,
        py: 6,
      }}
    >
      <Box
        sx={{
          width: 48,
          height: 48,
          borderRadius: "12px",
          bgcolor: "#F8FAFC",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          mb: 0.5,
        }}
      >
        <Icon size={22} strokeWidth={1.5} color={SUBTLE} />
      </Box>
      <Typography sx={{ fontSize: "15px", fontWeight: 600, color: TEXT }}>{title}</Typography>
      <Typography sx={{ fontSize: "14px", color: MUTED, textAlign: "center", maxWidth: 360 }}>
        {subtitle}
      </Typography>
    </Box>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

interface Props {
  schoolId: number;
}

export function VolunteerListTab({ schoolId }: Props) {
  const [data, setData] = useState<VolunteerListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<VolunteerCardType | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchVolunteers(schoolId);
        if (!cancelled) {
          setData(res);
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setError("Failed to load volunteers. Please try again.");
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [schoolId]);

  if (loading) return <VolunteerSkeleton />;

  if (error) {
    return <InfoState icon={AlertCircle} title="Could not load volunteers" subtitle={error} />;
  }

  if (!data) return null;

  if (data.status === "no_worknode") {
    return (
      <RichEmptyState
        badgeIcon={AlertCircle}
        badgeText="Setup required"
        heading="No Worknode configured"
        subtitle={
          data.message ??
          "No Worknode found for this school. Contact an admin to map it in Platform Commons before volunteers can be assigned here."
        }
        bullets={[
          {
            icon: Building2,
            text: "A Worknode links this school to volunteers tagged in Platform Commons",
          },
          { icon: UserCheck, text: "Once mapped, tagged volunteers appear here automatically" },
        ]}
        accent="#D97706"
      />
    );
  }

  if (data.status === "no_volunteers") {
    return (
      <RichEmptyState
        badgeIcon={UserCheck}
        badgeText="Get started"
        heading="No volunteers found"
        subtitle={
          data.message ??
          "No volunteers found for this school. To see volunteers here, add this school's workplace for that user in Platform Commons' user management — once tagged, they'll appear here and can be assigned to slots and mentoring circles."
        }
        bullets={[
          {
            icon: Building2,
            text: "Add this school as the volunteer's workplace in Platform Commons",
          },
          {
            icon: Clock,
            text: "Assign them to teaching slots and mentoring circles once they appear",
          },
          { icon: Heart, text: "Every volunteer mapped means one more class can run" },
        ]}
        accent="#7C3AED"
      />
    );
  }

  return (
    <Box sx={{ px: 4, pt: 3, pb: 6 }}>
      {/* Header */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 3 }}>
        <Typography
          sx={{
            fontSize: "12px",
            fontWeight: 700,
            color: SUBTLE,
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            whiteSpace: "nowrap",
          }}
        >
          Volunteers
        </Typography>
        <Box
          sx={{
            display: "inline-flex",
            alignItems: "center",
            px: 1,
            py: 0.25,
            borderRadius: "6px",
            bgcolor: "#EFF6FF",
            border: "1px solid #BFDBFE",
          }}
        >
          <Typography sx={{ fontSize: "11px", fontWeight: 600, color: "#1D4ED8" }}>
            {data.volunteers.length}
          </Typography>
        </Box>
        <Box sx={{ flex: 1, height: "1px", bgcolor: BORDER }} />
        {/* F-M9-3: only in the populated state — the empty states have nothing to export */}
        <ExportButton
          options={[{ label: "Volunteers", onExport: () => exportSchoolVolunteers(schoolId) }]}
        />
      </Box>

      {/* Volunteer list */}
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1.25 }}>
        {data.volunteers.map((v) => (
          <VolunteerCard key={v.userId} volunteer={v} onClick={() => setSelected(v)} />
        ))}
      </Box>

      <VolunteerDetailDrawer volunteer={selected} onClose={() => setSelected(null)} />
    </Box>
  );
}
