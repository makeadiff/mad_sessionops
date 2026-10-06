"use client";

/**
 * Shared admin building blocks. These mirror the look already used across the
 * app (ChildrenTab tables, EditChild/Deactivate dialogs, VolunteerDetailDrawer,
 * StatusTabs pills) so the M10 setup pages match the rest of the tool.
 */

import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Skeleton from "@mui/material/Skeleton";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { AlertTriangle, Check, CheckCircle2, Info, Search, X, XCircle } from "lucide-react";

// ── Design tokens ─────────────────────────────────────────────────────────────

export const BORDER = "#E2E8F0";
export const TH_BG = "#F8FAFC";
export const TH_TEXT = "#64748B";
export const ROW_HOVER = "#F8FAFC";
export const MUTED = "#94A3B8";
export const HEADING = "#0F172A";
export const TEXT = "#1E293B";
export const BODY = "#475569";
export const PRIMARY = "#2563EB";
export const PRIMARY_HOVER = "#1D4ED8";

// ── Buttons ───────────────────────────────────────────────────────────────────

export const primaryButtonSx = {
  fontSize: "13px",
  fontWeight: 600,
  bgcolor: PRIMARY,
  boxShadow: "none",
  textTransform: "none",
  "&:hover": { bgcolor: PRIMARY_HOVER, boxShadow: "none" },
  "&.Mui-disabled": { bgcolor: "#BFDBFE", color: "#fff" },
} as const;

export const secondaryButtonSx = {
  fontSize: "13px",
  fontWeight: 500,
  textTransform: "none",
  borderColor: BORDER,
  color: "#64748B",
  "&:hover": { borderColor: "#CBD5E1", bgcolor: "#F8FAFC" },
} as const;

export const dangerButtonSx = {
  fontSize: "13px",
  fontWeight: 500,
  textTransform: "none",
  borderColor: "#FECACA",
  color: "#DC2626",
  "&:hover": { borderColor: "#FCA5A5", bgcolor: "#FEF2F2" },
} as const;

/** Small inline row action ("Details", "Edit", "Open"). */
export const linkButtonSx = {
  fontSize: "12px",
  fontWeight: 600,
  color: PRIMARY,
  textTransform: "none",
  minWidth: 0,
  px: 1,
  "&:hover": { bgcolor: "#EFF6FF" },
} as const;

// ── Form fields ───────────────────────────────────────────────────────────────

export const fieldSx = {
  "& .MuiOutlinedInput-root": {
    fontSize: "13px",
    borderRadius: "8px",
    bgcolor: "#FAFAFA",
    "& fieldset": { borderColor: BORDER },
    "&:hover fieldset": { borderColor: "#CBD5E1" },
    "&.Mui-focused fieldset": { borderColor: PRIMARY, borderWidth: "1.5px" },
  },
  "& .MuiFormHelperText-root": { fontSize: "11px", mt: 0.5, mx: 0 },
} as const;

export function FieldLabel({
  htmlFor,
  id,
  required,
  children,
}: {
  htmlFor?: string;
  id?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <Typography
      component="label"
      htmlFor={htmlFor}
      id={id}
      sx={{
        display: "block",
        fontSize: "12px",
        fontWeight: 600,
        color: "#334155",
        mb: 0.625,
        // Marker via CSS so the label's accessible name stays exactly the text.
        ...(required && { "&::after": { content: '"*"', color: "#EF4444", ml: 0.25 } }),
      }}
    >
      {children}
    </Typography>
  );
}

export function SearchField({
  value,
  onChange,
  placeholder,
  width = 240,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  width?: number | string;
}) {
  return (
    <TextField
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      size="small"
      sx={{ width, ...fieldSx }}
      InputProps={{
        startAdornment: (
          <InputAdornment position="start">
            <Search size={13} color={MUTED} />
          </InputAdornment>
        ),
        endAdornment: value ? (
          <InputAdornment position="end">
            <IconButton
              size="small"
              onClick={() => onChange("")}
              edge="end"
              sx={{ p: 0.25 }}
              aria-label="Clear search"
            >
              <X size={13} color={MUTED} />
            </IconButton>
          </InputAdornment>
        ) : undefined,
      }}
    />
  );
}

// ── Page intro (description + actions under the shell's title bar) ─────────────

export function PageIntro({
  description,
  actions,
}: {
  description: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: 2,
        mb: 2.5,
      }}
    >
      <Typography sx={{ fontSize: "13px", color: TH_TEXT, maxWidth: 640, lineHeight: 1.55 }}>
        {description}
      </Typography>
      {actions && <Box sx={{ display: "flex", gap: 1, flexShrink: 0 }}>{actions}</Box>}
    </Box>
  );
}

// ── Tables ────────────────────────────────────────────────────────────────────

export function TableShell({ children }: { children: ReactNode }) {
  return (
    <TableContainer
      sx={{
        border: `1px solid ${BORDER}`,
        borderRadius: "10px",
        overflow: "hidden",
        bgcolor: "#fff",
      }}
    >
      {children}
    </TableContainer>
  );
}

export type HeadColumn = string | { label: ReactNode; align?: "left" | "right"; width?: number };

export function HeadRow({ columns }: { columns: HeadColumn[] }) {
  return (
    <TableRow sx={{ bgcolor: TH_BG }}>
      {columns.map((c, i) => {
        const col = typeof c === "string" ? { label: c } : c;
        return (
          <TableCell
            key={i}
            align={col.align}
            padding={col.width === 48 ? "checkbox" : undefined}
            sx={{
              fontSize: "11px",
              fontWeight: 600,
              color: TH_TEXT,
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              py: 1.25,
              width: col.width,
              borderBottom: `1px solid ${BORDER}`,
              whiteSpace: "nowrap",
            }}
          >
            {col.label}
          </TableCell>
        );
      })}
    </TableRow>
  );
}

export const cellSx = {
  py: 1.25,
  fontSize: "13px",
  color: BODY,
  borderBottom: `1px solid ${BORDER}`,
} as const;

export const nameCellSx = { ...cellSx, fontWeight: 500, color: TEXT } as const;

export const bodyRowSx = {
  "&:hover": { bgcolor: ROW_HOVER },
  "&:last-child td": { borderBottom: "none" },
} as const;

export function LoadingRows({ cols, rows = 4 }: { cols: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <TableRow key={i}>
          {Array.from({ length: cols }).map((__, j) => (
            <TableCell key={j} sx={{ py: 1.5, borderBottom: `1px solid ${BORDER}` }}>
              <Skeleton variant="text" width={j === 0 ? 140 : 60} height={16} />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

export function EmptyRow({ cols, message }: { cols: number; message: string }) {
  return (
    <TableRow>
      <TableCell colSpan={cols} sx={{ py: 5, textAlign: "center", borderBottom: "none" }}>
        <Typography sx={{ fontSize: "13px", color: MUTED }}>{message}</Typography>
      </TableCell>
    </TableRow>
  );
}

// ── Status pill (same shape as the Active/Inactive chips elsewhere) ─────────────

export type Tone = "success" | "warning" | "error" | "info" | "neutral" | "purple";

const TONES: Record<Tone, { bg: string; fg: string }> = {
  success: { bg: "#DCFCE7", fg: "#16A34A" },
  warning: { bg: "#FEF3C7", fg: "#B45309" },
  error: { bg: "#FEE2E2", fg: "#DC2626" },
  info: { bg: "#DBEAFE", fg: "#1D4ED8" },
  neutral: { bg: "#F1F5F9", fg: "#64748B" },
  purple: { bg: "#EDE9FE", fg: "#6D28D9" },
};

export function Pill({ label, tone }: { label: ReactNode; tone: Tone }) {
  const t = TONES[tone];
  return (
    <Box
      component="span"
      sx={{
        display: "inline-flex",
        alignItems: "center",
        height: 20,
        px: 0.875,
        borderRadius: "4px",
        bgcolor: t.bg,
        color: t.fg,
        fontSize: "11px",
        fontWeight: 600,
        whiteSpace: "nowrap",
        lineHeight: 1,
      }}
    >
      {label}
    </Box>
  );
}

// ── Segmented tabs (same look as the Children status tabs) ─────────────────────

export function SegmentedTabs<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: T;
  options: { value: T; label: string; count?: number | null }[];
  onChange: (v: T) => void;
  ariaLabel?: string;
}) {
  return (
    <Box
      role="tablist"
      aria-label={ariaLabel}
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
      {options.map((opt) => {
        const active = value === opt.value;
        return (
          <Box
            key={opt.value}
            component="button"
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt.value)}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 0.75,
              px: 1.25,
              py: 0.75,
              border: "none",
              borderRadius: "6px",
              cursor: "pointer",
              font: "inherit",
              transition: "all 0.12s ease",
              bgcolor: active ? "#fff" : "transparent",
              boxShadow: active ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
              "&:hover": { bgcolor: active ? "#fff" : "#EFF6FF" },
            }}
          >
            <Typography
              component="span"
              sx={{
                fontSize: "12px",
                fontWeight: active ? 600 : 500,
                color: active ? HEADING : TH_TEXT,
                lineHeight: 1,
              }}
            >
              {opt.label}
            </Typography>
            {opt.count !== undefined && opt.count !== null && (
              <Box
                component="span"
                sx={{
                  minWidth: 18,
                  height: 18,
                  px: 0.75,
                  borderRadius: "5px",
                  bgcolor: active ? PRIMARY : BORDER,
                  color: active ? "#fff" : TH_TEXT,
                  fontSize: "10px",
                  fontWeight: 700,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {opt.count}
              </Box>
            )}
          </Box>
        );
      })}
    </Box>
  );
}

// ── Notice (inline banner) ────────────────────────────────────────────────────

const NOTICE: Record<
  "info" | "warning" | "error" | "success",
  { bg: string; border: string; fg: string; Icon: typeof Info }
> = {
  info: { bg: "#EFF6FF", border: "#BFDBFE", fg: "#1E40AF", Icon: Info },
  warning: { bg: "#FFFBEB", border: "#FDE68A", fg: "#92400E", Icon: AlertTriangle },
  error: { bg: "#FEF2F2", border: "#FECACA", fg: "#991B1B", Icon: XCircle },
  success: { bg: "#F0FDF4", border: "#BBF7D0", fg: "#166534", Icon: CheckCircle2 },
};

export function Notice({
  tone = "info",
  children,
  action,
}: {
  tone?: keyof typeof NOTICE;
  children: ReactNode;
  action?: ReactNode;
}) {
  const n = NOTICE[tone];
  return (
    <Box
      role={tone === "error" || tone === "warning" ? "alert" : "status"}
      sx={{
        display: "flex",
        alignItems: "flex-start",
        gap: 1.25,
        px: 1.75,
        py: 1.25,
        borderRadius: "8px",
        border: `1px solid ${n.border}`,
        bgcolor: n.bg,
      }}
    >
      <n.Icon size={15} color={n.fg} style={{ flexShrink: 0, marginTop: 1 }} />
      <Typography component="div" sx={{ flex: 1, fontSize: "13px", color: n.fg, lineHeight: 1.5 }}>
        {children}
      </Typography>
      {action}
    </Box>
  );
}

// ── Side panel (right drawer with header / scroll body / footer) ───────────────

export function SidePanel({
  open,
  title,
  subtitle,
  onClose,
  children,
  footer,
  width = 440,
  closeLabel = "Close details",
}: {
  open: boolean;
  title: ReactNode;
  subtitle?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
  closeLabel?: string;
}) {
  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          width,
          maxWidth: "100vw",
          borderLeft: `1.5px solid ${BORDER}`,
          boxShadow: "-4px 0 24px rgba(0,0,0,0.06)",
        },
      }}
    >
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
        <Box
          sx={{
            px: 2.5,
            pt: 2.5,
            pb: 2,
            borderBottom: `1px solid ${BORDER}`,
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 1.5,
          }}
        >
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ fontSize: "15px", fontWeight: 700, color: HEADING }}>
              {title}
            </Typography>
            {subtitle && (
              <Typography component="div" sx={{ fontSize: "12px", color: MUTED, mt: 0.25 }}>
                {subtitle}
              </Typography>
            )}
          </Box>
          <IconButton
            size="small"
            onClick={onClose}
            aria-label={closeLabel}
            sx={{ color: MUTED, "&:hover": { bgcolor: "#F1F5F9", color: "#475569" } }}
          >
            <X size={16} />
          </IconButton>
        </Box>
        <Box
          sx={{
            flex: 1,
            overflowY: "auto",
            px: 2.5,
            py: 2,
            display: "flex",
            flexDirection: "column",
            gap: 2.25,
          }}
        >
          {children}
        </Box>
        {footer && (
          <Box
            sx={{
              px: 2.5,
              py: 1.75,
              borderTop: `1px solid ${BORDER}`,
              display: "flex",
              gap: 1,
              justifyContent: "flex-end",
              flexWrap: "wrap",
            }}
          >
            {footer}
          </Box>
        )}
      </Box>
    </Drawer>
  );
}

/** Small uppercase section heading used inside panels. */
export function PanelHeading({ children }: { children: ReactNode }) {
  return (
    <Typography
      sx={{
        fontSize: "10px",
        fontWeight: 700,
        color: MUTED,
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        mb: 0.75,
      }}
    >
      {children}
    </Typography>
  );
}

/** Label/value line inside a panel ("5th → 6th   71"). */
export function KeyValue({ label, value }: { label: ReactNode; value: ReactNode }) {
  return (
    <Box
      sx={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        py: 0.75,
        borderBottom: `1px dashed ${BORDER}`,
        "&:last-of-type": { borderBottom: "none" },
      }}
    >
      <Typography sx={{ fontSize: "13px", color: BODY }}>{label}</Typography>
      <Typography sx={{ fontSize: "13px", fontWeight: 600, color: TEXT }}>{value}</Typography>
    </Box>
  );
}

// ── Dialog shell (same as EditChild / Deactivate dialogs) ──────────────────────

export function DialogShell({
  open,
  onClose,
  title,
  subtitle,
  children,
  actions,
  maxWidth = "xs",
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  actions: ReactNode;
  maxWidth?: "xs" | "sm" | "md";
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth={maxWidth}
      fullWidth
      PaperProps={{ sx: { borderRadius: "14px", boxShadow: "0 20px 60px rgba(0,0,0,0.12)" } }}
    >
      <DialogTitle
        component="div"
        sx={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          pt: 2.5,
          pb: 1.5,
          px: 3,
          borderBottom: `1px solid ${BORDER}`,
        }}
      >
        <Box>
          <Typography component="h2" sx={{ fontSize: "15px", fontWeight: 700, color: HEADING }}>
            {title}
          </Typography>
          {subtitle && (
            <Typography sx={{ fontSize: "12px", color: MUTED, mt: 0.25 }}>{subtitle}</Typography>
          )}
        </Box>
        <IconButton
          size="small"
          onClick={onClose}
          aria-label="Close"
          sx={{ mt: 0.25, color: MUTED, "&:hover": { bgcolor: "#F1F5F9", color: "#475569" } }}
        >
          <X size={16} />
        </IconButton>
      </DialogTitle>
      <DialogContent sx={{ px: 3, pt: "20px !important", pb: 1 }}>{children}</DialogContent>
      <DialogActions sx={{ px: 3, py: 2, borderTop: `1px solid ${BORDER}`, gap: 1 }}>
        {actions}
      </DialogActions>
    </Dialog>
  );
}

// ── Step indicator (wizard) ───────────────────────────────────────────────────

export function StepIndicator({ steps, active }: { steps: string[]; active: number }) {
  return (
    <Box
      component="ol"
      aria-label="Progress"
      sx={{ display: "flex", alignItems: "center", gap: 1, listStyle: "none", m: 0, p: 0 }}
    >
      {steps.map((label, i) => {
        const done = i < active;
        const current = i === active;
        return (
          <Box
            component="li"
            key={label}
            aria-current={current ? "step" : undefined}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1,
              flex: i < steps.length - 1 ? 1 : "none",
            }}
          >
            <Box
              sx={{
                width: 22,
                height: 22,
                borderRadius: "50%",
                flexShrink: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "11px",
                fontWeight: 700,
                bgcolor: done ? "#DCFCE7" : current ? PRIMARY : "#F1F5F9",
                color: done ? "#16A34A" : current ? "#fff" : MUTED,
              }}
            >
              {done ? <Check size={12} strokeWidth={3} /> : i + 1}
            </Box>
            <Typography
              sx={{
                fontSize: "12px",
                fontWeight: current ? 700 : 500,
                color: current ? HEADING : done ? BODY : MUTED,
                whiteSpace: "nowrap",
              }}
            >
              {label}
            </Typography>
            {i < steps.length - 1 && (
              <Box
                sx={{ flex: 1, height: "1px", bgcolor: done ? "#BBF7D0" : BORDER, minWidth: 16 }}
              />
            )}
          </Box>
        );
      })}
    </Box>
  );
}

// ── Stat tile (preview / run summaries) ───────────────────────────────────────

export function StatTile({
  label,
  value,
  accent = TEXT,
  testId,
}: {
  label: string;
  value: ReactNode;
  accent?: string;
  testId?: string;
}) {
  return (
    <Box
      data-testid={testId}
      sx={{
        flex: 1,
        minWidth: 120,
        border: `1px solid ${BORDER}`,
        borderRadius: "10px",
        bgcolor: "#fff",
        px: 2,
        py: 1.5,
      }}
    >
      <Typography sx={{ fontSize: "20px", fontWeight: 700, color: accent, lineHeight: 1.15 }}>
        {value}
      </Typography>
      <Typography sx={{ fontSize: "11px", color: TH_TEXT, fontWeight: 500, mt: 0.25 }}>
        {label}
      </Typography>
    </Box>
  );
}

// ── Type-to-confirm (for actions that are hard to reverse) ─────────────────────

/** Case/space-insensitive match, so "Global Kids  school" still counts. */
export function confirmMatches(value: string, phrase: string): boolean {
  const norm = (s: string) => s.trim().replace(/\s+/g, " ").toLowerCase();
  return norm(value) !== "" && norm(value) === norm(phrase);
}

export function TypeToConfirm({
  phrase,
  value,
  onChange,
  disabled,
}: {
  phrase: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <Box
      sx={{
        mt: 2,
        p: 1.5,
        borderRadius: "8px",
        bgcolor: "#FEF2F2",
        border: "1px solid #FECACA",
      }}
    >
      <Typography sx={{ fontSize: "12px", color: "#991B1B", mb: 1, lineHeight: 1.5 }}>
        To confirm, type{" "}
        <Box component="strong" sx={{ fontWeight: 700, userSelect: "all" }}>
          {phrase}
        </Box>{" "}
        below.
      </Typography>
      <TextField
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        size="small"
        fullWidth
        autoComplete="off"
        placeholder={phrase}
        inputProps={{ "aria-label": "Type to confirm" }}
        sx={{
          ...fieldSx,
          "& .MuiOutlinedInput-root": { ...fieldSx["& .MuiOutlinedInput-root"], bgcolor: "#fff" },
        }}
      />
    </Box>
  );
}
