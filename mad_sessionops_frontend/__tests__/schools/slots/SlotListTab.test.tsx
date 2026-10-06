import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SlotListTab } from "@/components/schools/slots/SlotListTab";
import type { SlotItem } from "@/lib/api/services/slots.service";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/lib/api/services/slots.service", () => ({
  fetchSlots: vi.fn(),
}));

vi.mock("@/lib/api/services/exports.service", () => ({
  exportSchoolTimetable: vi.fn().mockResolvedValue(undefined),
}));

// Slot detail/grid fetch their own data; not under test here.
vi.mock("@/components/schools/slots/SlotDetail", () => ({ SlotDetail: () => null }));
vi.mock("@/components/schools/slots/SlotGridView", () => ({ SlotGridView: () => null }));

vi.mock("react-hot-toast", () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

import { fetchSlots } from "@/lib/api/services/slots.service";
import { exportSchoolTimetable } from "@/lib/api/services/exports.service";

const SLOT: SlotItem = {
  slotId: 1,
  slotName: "Monday 10:00",
  dayOfWeek: "monday",
  startTime: "10:00:00",
  endTime: "11:00:00",
  recurring: true,
  slotClassCount: 1,
};

describe("SlotListTab — F-M9-4 export", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("test_export_button_calls_timetable_export", async () => {
    vi.mocked(fetchSlots).mockResolvedValue([SLOT]);

    render(<SlotListTab schoolId={580} canModify={false} />);

    const button = await screen.findByRole("button", { name: /export csv/i });
    expect(button).not.toBeDisabled();
    await userEvent.click(button);

    await waitFor(() => expect(exportSchoolTimetable).toHaveBeenCalledWith(580));
  });

  it("test_export_button_disabled_when_no_slots", async () => {
    vi.mocked(fetchSlots).mockResolvedValue([]);

    render(<SlotListTab schoolId={580} />);

    const button = await screen.findByRole("button", { name: /export csv/i });
    expect(button).toBeDisabled();
  });
});
