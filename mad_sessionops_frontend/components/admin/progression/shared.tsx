"use client";

import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { AlertTriangle, XCircle } from "lucide-react";
import type {
  Issue,
  PrecheckStatus,
  RunStatus,
  SchoolRunStatus,
} from "@/lib/api/services/progression.service";
import { BODY, PanelHeading, Pill, SidePanel, type Tone } from "../adminUi";

// ── Status pills ──────────────────────────────────────────────────────────────

const PRECHECK: Record<PrecheckStatus, { label: string; tone: Tone }> = {
  ready: { label: "Ready", tone: "success" },
  warning: { label: "Warning", tone: "warning" },
  blocked: { label: "Blocked", tone: "error" },
};

export function PrecheckChip({ status }: { status: PrecheckStatus }) {
  const c = PRECHECK[status];
  return <Pill label={c.label} tone={c.tone} />;
}

const SCHOOL_RUN: Record<SchoolRunStatus, { label: string; tone: Tone }> = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Running", tone: "info" },
  completed: { label: "Done", tone: "success" },
  failed: { label: "Failed", tone: "error" },
  undone: { label: "Undone", tone: "purple" },
  released: { label: "Released", tone: "neutral" },
};

export function RunStatusChip({ status }: { status: SchoolRunStatus }) {
  const c = SCHOOL_RUN[status];
  return <Pill label={c.label} tone={c.tone} />;
}

const RUN: Record<RunStatus, { label: string; tone: Tone }> = {
  in_progress: { label: "In progress", tone: "info" },
  completed: { label: "Completed", tone: "success" },
  completed_with_failures: { label: "Completed with failures", tone: "warning" },
};

export function RunChip({ status }: { status: RunStatus }) {
  const c = RUN[status] ?? { label: status, tone: "neutral" as Tone };
  return <Pill label={c.label} tone={c.tone} />;
}

// ── Side drawer (per-school details) ──────────────────────────────────────────

export function SchoolDrawer({
  open,
  title,
  subtitle,
  onClose,
  footer,
  children,
}: {
  open: boolean;
  title: string;
  subtitle?: string | null;
  onClose: () => void;
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <SidePanel open={open} title={title} subtitle={subtitle} onClose={onClose} footer={footer}>
      {children}
    </SidePanel>
  );
}

export function IssueList({
  title,
  issues,
  tone = "warning",
}: {
  title: string;
  issues: Issue[];
  tone?: "warning" | "error";
}) {
  if (issues.length === 0) return null;
  const Icon = tone === "error" ? XCircle : AlertTriangle;
  const color = tone === "error" ? "#DC2626" : "#D97706";
  return (
    <Box>
      <PanelHeading>
        {title} ({issues.length})
      </PanelHeading>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
        {issues.map((i) => (
          <Box
            key={i.code}
            sx={{
              display: "flex",
              gap: 1,
              alignItems: "flex-start",
              px: 1.25,
              py: 1,
              borderRadius: "8px",
              bgcolor: tone === "error" ? "#FEF2F2" : "#FFFBEB",
            }}
          >
            <Icon size={14} color={color} style={{ flexShrink: 0, marginTop: 2 }} />
            <Typography sx={{ fontSize: "13px", color: BODY, lineHeight: 1.5 }}>
              {i.message}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

/** First issue's message for a compact table cell, plus "+N more". */
export function firstIssue(blockers: Issue[], warnings: Issue[]): string | null {
  const all = [...blockers, ...warnings];
  if (all.length === 0) return null;
  return all.length > 1 ? `${all[0].message} (+${all.length - 1} more)` : all[0].message;
}
