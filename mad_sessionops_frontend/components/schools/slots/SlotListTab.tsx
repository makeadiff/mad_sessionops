"use client";

import { useState, useEffect, useCallback } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import { Plus, Clock, Pencil, Trash2, CalendarDays, LayoutList, Table } from "lucide-react";
import { fetchSlots, type SlotItem, type DayOfWeek } from "@/lib/api/services/slots.service";
import { SlotDetail } from "./SlotDetail";
import { AddSlotModal } from "./AddSlotModal";
import { EditSlotModal } from "./EditSlotModal";
import { DeleteSlotModal } from "./DeleteSlotModal";
import { SlotGridView } from "./SlotGridView";
import { formatTime } from "./SlotCard";
import { ExportButton } from "@/components/ui/ExportButton";
import { exportSchoolTimetable } from "@/lib/api/services/exports.service";
import toast from "react-hot-toast";

// ── Constants ──────────────────────────────────────────────────────────────────

const DAY_ORDER: DayOfWeek[] = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
];

const DAY_SHORT: Record<DayOfWeek, string> = {
  monday: "MON",
  tuesday: "TUE",
  wednesday: "WED",
  thursday: "THU",
  friday: "FRI",
  saturday: "SAT",
  sunday: "SUN",
};

const DAY_COLOR: Record<DayOfWeek, { bg: string; text: string; border: string }> = {
  monday: { bg: "#EFF6FF", text: "#1D4ED8", border: "#BFDBFE" },
  tuesday: { bg: "#F0FDF4", text: "#15803D", border: "#BBF7D0" },
  wednesday: { bg: "#FFF7ED", text: "#C2410C", border: "#FED7AA" },
  thursday: { bg: "#FDF4FF", text: "#7E22CE", border: "#E9D5FF" },
  friday: { bg: "#FFF1F2", text: "#BE123C", border: "#FECDD3" },
  saturday: { bg: "#F5F3FF", text: "#6D28D9", border: "#DDD6FE" },
  sunday: { bg: "#F5F3FF", text: "#6D28D9", border: "#DDD6FE" },
};

const BORDER = "#E2E8F0";
const MUTED = "#94A3B8";

function sortSlots(slots: SlotItem[]): SlotItem[] {
  return [...slots].sort((a, b) => {
    const dd = DAY_ORDER.indexOf(a.dayOfWeek) - DAY_ORDER.indexOf(b.dayOfWeek);
    return dd !== 0 ? dd : a.startTime.localeCompare(b.startTime);
  });
}

// ── SlotAgendaCard ─────────────────────────────────────────────────────────────

function SlotAgendaCard({
  slot,
  schoolId,
  canModify,
  onEdit,
  onDelete,
  onCountChange,
}: {
  slot: SlotItem;
  schoolId: number;
  canModify: boolean;
  onEdit: (s: SlotItem) => void;
  onDelete: (s: SlotItem) => void;
  onCountChange: (slotId: number, delta: number) => void;
}) {
  const color = DAY_COLOR[slot.dayOfWeek];

  return (
    <Box
      sx={{
        borderRadius: "12px",
        border: `1.5px solid ${BORDER}`,
        bgcolor: "#fff",
        overflow: "hidden",
        transition: "box-shadow 0.15s ease",
        "&:hover": { boxShadow: "0 4px 20px rgba(0,0,0,0.06)" },
      }}
    >
      {/* ── Slot header ── */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          px: 2.5,
          py: 1.5,
          bgcolor: "#FAFBFF",
          borderBottom: `1px solid ${BORDER}`,
        }}
      >
        {/* Day chip */}
        <Box
          sx={{
            px: 1.25,
            py: 0.5,
            borderRadius: "8px",
            bgcolor: color.bg,
            border: `1.5px solid ${color.border}`,
            flexShrink: 0,
          }}
        >
          <Typography
            sx={{ fontSize: "11px", fontWeight: 800, color: color.text, letterSpacing: "0.05em" }}
          >
            {DAY_SHORT[slot.dayOfWeek]}
          </Typography>
        </Box>

        {/* Time range */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.625, flex: 1, minWidth: 0 }}>
          <Clock size={13} color={MUTED} strokeWidth={1.75} />
          <Typography sx={{ fontSize: "13px", fontWeight: 600, color: "#1E293B" }}>
            {formatTime(slot.startTime)}
            <Typography component="span" sx={{ color: MUTED, fontWeight: 400 }}>
              {" "}
              –{" "}
            </Typography>
            {formatTime(slot.endTime)}
          </Typography>
          <Typography
            sx={{
              fontSize: "12px",
              color: MUTED,
              ml: 0.5,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            · {slot.slotName}
          </Typography>
        </Box>

        {/* Class count */}
        {slot.slotClassCount > 0 && (
          <Box sx={{ px: 1, py: 0.25, borderRadius: "6px", bgcolor: "#F1F5F9", flexShrink: 0 }}>
            <Typography sx={{ fontSize: "11px", fontWeight: 600, color: "#475569" }}>
              {slot.slotClassCount} {slot.slotClassCount === 1 ? "class" : "classes"}
            </Typography>
          </Box>
        )}

        {/* Edit / Delete */}
        {canModify && (
          <Box sx={{ display: "flex", gap: 0.25, flexShrink: 0 }}>
            <IconButton
              size="small"
              onClick={() => onEdit(slot)}
              sx={{ p: 0.5, color: MUTED, "&:hover": { color: "#2563EB", bgcolor: "#EFF6FF" } }}
            >
              <Pencil size={13} />
            </IconButton>
            <IconButton
              size="small"
              onClick={() => onDelete(slot)}
              sx={{ p: 0.5, color: MUTED, "&:hover": { color: "#EF4444", bgcolor: "#FEF2F2" } }}
            >
              <Trash2 size={13} />
            </IconButton>
          </Box>
        )}
      </Box>

      {/* ── Slot-class list — always visible, no click needed ── */}
      <SlotDetail
        slot={slot}
        schoolId={schoolId}
        canModify={canModify}
        onSlotClassCountChange={(delta) => onCountChange(slot.slotId, delta)}
      />
    </Box>
  );
}

// ── Props ──────────────────────────────────────────────────────────────────────

interface SlotListTabProps {
  schoolId: number;
  canModify?: boolean;
}

// ── Main component ─────────────────────────────────────────────────────────────

export function SlotListTab({ schoolId, canModify = true }: SlotListTabProps) {
  const [slots, setSlots] = useState<SlotItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<"agenda" | "grid">("agenda");
  const [addOpen, setAddOpen] = useState(false);
  const [editingSlot, setEditingSlot] = useState<SlotItem | null>(null);
  const [deletingSlot, setDeletingSlot] = useState<SlotItem | null>(null);

  const loadSlots = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchSlots(schoolId);
      setSlots(sortSlots(data));
    } catch {
      toast.error("Failed to load slots.");
    } finally {
      setLoading(false);
    }
  }, [schoolId]);

  useEffect(() => {
    loadSlots();
  }, [loadSlots]);

  function handleAdded(slot: SlotItem) {
    setSlots((prev) => sortSlots([...prev, slot]));
    toast.success(`"${slot.slotName}" created.`);
  }

  function handleSaved(updated: SlotItem) {
    setSlots((prev) => sortSlots(prev.map((s) => (s.slotId === updated.slotId ? updated : s))));
    toast.success(`"${updated.slotName}" updated.`);
  }

  function handleDeleted(slotId: number) {
    setSlots((prev) => prev.filter((s) => s.slotId !== slotId));
    toast.success("Slot deleted.");
  }

  function handleCountChange(slotId: number, delta: number) {
    setSlots((prev) =>
      prev.map((s) =>
        s.slotId === slotId ? { ...s, slotClassCount: s.slotClassCount + delta } : s
      )
    );
  }

  const totalClasses = slots.reduce((s, sl) => s + sl.slotClassCount, 0);

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress size={28} />
      </Box>
    );
  }

  return (
    <Box sx={{ px: 4, pt: 3, pb: 6 }}>
      {/* Header */}
      <Box
        sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", mb: 3 }}
      >
        <Box>
          <Typography sx={{ fontSize: "16px", fontWeight: 700, color: "#1E293B" }}>
            Weekly Slots
          </Typography>
          {slots.length > 0 && (
            <Typography sx={{ fontSize: "12px", color: MUTED, mt: 0.25 }}>
              {slots.length} {slots.length === 1 ? "slot" : "slots"}
              {" · "}
              {totalClasses} {totalClasses === 1 ? "class assignment" : "class assignments"}
            </Typography>
          )}
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          {/* F-M9-4: timetable CSV — nothing to export until a slot exists */}
          <ExportButton
            disabled={slots.length === 0}
            options={[{ label: "Timetable", onExport: () => exportSchoolTimetable(schoolId) }]}
          />
          {/* View toggle */}
          <Box
            sx={{
              display: "flex",
              border: `1.5px solid ${BORDER}`,
              borderRadius: "8px",
              overflow: "hidden",
            }}
          >
            <Tooltip title="Agenda view" placement="top">
              <Box
                onClick={() => setViewMode("agenda")}
                sx={{
                  px: 1.25,
                  py: 0.75,
                  cursor: "pointer",
                  bgcolor: viewMode === "agenda" ? "#EFF6FF" : "#fff",
                  borderRight: `1px solid ${BORDER}`,
                  display: "flex",
                  alignItems: "center",
                  transition: "background 0.12s ease",
                  "&:hover": { bgcolor: viewMode === "agenda" ? "#EFF6FF" : "#F8FAFC" },
                }}
              >
                <LayoutList
                  size={15}
                  color={viewMode === "agenda" ? "#2563EB" : MUTED}
                  strokeWidth={2}
                />
              </Box>
            </Tooltip>
            <Tooltip title="Schedule grid" placement="top">
              <Box
                onClick={() => setViewMode("grid")}
                sx={{
                  px: 1.25,
                  py: 0.75,
                  cursor: "pointer",
                  bgcolor: viewMode === "grid" ? "#EFF6FF" : "#fff",
                  display: "flex",
                  alignItems: "center",
                  transition: "background 0.12s ease",
                  "&:hover": { bgcolor: viewMode === "grid" ? "#EFF6FF" : "#F8FAFC" },
                }}
              >
                <Table size={15} color={viewMode === "grid" ? "#2563EB" : MUTED} strokeWidth={2} />
              </Box>
            </Tooltip>
          </Box>

          {canModify && (
            <Button
              variant="contained"
              size="small"
              startIcon={<Plus size={14} />}
              onClick={() => setAddOpen(true)}
              sx={{
                bgcolor: "#2563EB",
                boxShadow: "none",
                "&:hover": { bgcolor: "#1D4ED8", boxShadow: "none" },
              }}
            >
              Add Slot
            </Button>
          )}
        </Box>
      </Box>

      {/* Grid view */}
      {viewMode === "grid" && (
        <SlotGridView
          schoolId={schoolId}
          slots={slots}
          canModify={canModify}
          onCountChange={handleCountChange}
          onEditSlot={setEditingSlot}
          onDeleteSlot={setDeletingSlot}
        />
      )}

      {/* Agenda view */}
      {viewMode === "agenda" &&
        (slots.length === 0 ? (
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              minHeight: 320,
              gap: 1.5,
              border: `1.5px dashed ${BORDER}`,
              borderRadius: "14px",
              bgcolor: "#FAFAFA",
            }}
          >
            <Box
              sx={{
                width: 48,
                height: 48,
                borderRadius: "12px",
                bgcolor: "#FFF7ED",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <CalendarDays size={22} strokeWidth={1.5} color="#EA580C" />
            </Box>
            <Typography sx={{ fontSize: "15px", fontWeight: 600, color: "#1E293B" }}>
              No slots configured yet.
            </Typography>
            <Typography sx={{ fontSize: "13px", color: MUTED, textAlign: "center", maxWidth: 300 }}>
              {canModify
                ? "Click 'Add Slot' to schedule the first teaching slot."
                : "No slots have been configured for this school."}
            </Typography>
            {canModify && (
              <Button
                variant="contained"
                size="small"
                startIcon={<Plus size={14} />}
                onClick={() => setAddOpen(true)}
                sx={{ mt: 0.5 }}
              >
                Add Slot
              </Button>
            )}
          </Box>
        ) : (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {slots.map((slot) => (
              <SlotAgendaCard
                key={slot.slotId}
                slot={slot}
                schoolId={schoolId}
                canModify={canModify}
                onEdit={setEditingSlot}
                onDelete={setDeletingSlot}
                onCountChange={handleCountChange}
              />
            ))}

            {canModify && (
              <Box
                onClick={() => setAddOpen(true)}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 0.75,
                  py: 2,
                  borderRadius: "12px",
                  border: `1.5px dashed ${BORDER}`,
                  cursor: "pointer",
                  transition: "all 0.12s ease",
                  "&:hover": { borderColor: "#93C5FD", bgcolor: "#F0F9FF" },
                }}
              >
                <Plus size={14} color={MUTED} />
                <Typography sx={{ fontSize: "13px", color: MUTED, fontWeight: 500 }}>
                  Add another slot
                </Typography>
              </Box>
            )}
          </Box>
        ))}

      {/* Modals */}
      <AddSlotModal
        open={addOpen}
        schoolId={schoolId}
        onClose={() => setAddOpen(false)}
        onAdded={handleAdded}
      />
      {editingSlot && (
        <EditSlotModal
          open={Boolean(editingSlot)}
          schoolId={schoolId}
          slot={editingSlot}
          onClose={() => setEditingSlot(null)}
          onSaved={handleSaved}
        />
      )}
      {deletingSlot && (
        <DeleteSlotModal
          open={Boolean(deletingSlot)}
          schoolId={schoolId}
          slot={deletingSlot}
          onClose={() => setDeletingSlot(null)}
          onDeleted={handleDeleted}
        />
      )}
    </Box>
  );
}
