import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RunsTab } from "@/components/admin/progression/RunsTab";
import type { RunDetail, RunSchool } from "@/lib/api/services/progression.service";

vi.mock("@/lib/api/services/progression.service", () => ({
  listRuns: vi.fn(),
  getRun: vi.fn(),
  getRunSchool: vi.fn(),
  executeSchool: vi.fn(),
  releaseSchool: vi.fn(),
  undoSchool: vi.fn(),
}));
vi.mock("@/lib/toast/toast", () => ({ showApiError: vi.fn(), showSuccess: vi.fn() }));

import {
  executeSchool,
  getRun,
  getRunSchool,
  listRuns,
  undoSchool,
} from "@/lib/api/services/progression.service";

const RUN = {
  runId: 9,
  status: "in_progress" as const,
  yearMoves: [
    { label: "2025-2026 → 2026-2027", schools: 2 },
    { label: "2026-2027 → 2027-2028", schools: 1 },
  ],
  startedByName: "Asha Admin",
  startedAt: "2026-09-30T10:00:00Z",
  finishedAt: null,
  cleanup: {},
  schoolCounts: { completed: 1, queued: 2 },
};

function school(
  id: number,
  status: RunSchool["status"],
  extra: Partial<RunSchool> = {}
): RunSchool {
  return {
    schoolProgressionId: id * 10,
    runId: 9,
    schoolId: id,
    schoolName: `School ${id}`,
    fromYearLabel: "2025-2026",
    toYearLabel: "2026-2027",
    status,
    error: null,
    counts: {},
    warnings: [],
    graduateClassIds: [],
    graduateChildIds: [],
    startedAt: null,
    finishedAt: null,
    canUndo: false,
    undoBlockReason: null,
    ...extra,
  };
}

function detail(schools: RunSchool[]): RunDetail {
  return { ...RUN, schools };
}

async function openRun() {
  render(<RunsTab />);
  await userEvent.click(await screen.findByRole("button", { name: "Open" }));
}

describe("RunsTab — F-M10-9", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listRuns).mockResolvedValue([RUN]);
  });

  it("lists runs", async () => {
    render(<RunsTab />);
    expect(await screen.findByText("#9")).toBeInTheDocument();
    // One run can move schools from different years; each move is listed.
    expect(screen.getByText("2025-2026 → 2026-2027 (2)")).toBeInTheDocument();
    expect(screen.getByText("2026-2027 → 2027-2028 (1)")).toBeInTheDocument();
    expect(screen.getByText("1 completed · 2 queued")).toBeInTheDocument();
  });

  it("Resume executes the queued schools in order", async () => {
    vi.mocked(getRun).mockResolvedValue(
      detail([school(1, "completed"), school(2, "queued"), school(3, "queued")])
    );
    vi.mocked(executeSchool).mockImplementation(async (_r, id) => ({
      schoolId: id,
      status: "completed",
      error: null,
    }));

    await openRun();
    await userEvent.click(await screen.findByRole("button", { name: "Resume (2 queued)" }));

    await waitFor(() => expect(executeSchool).toHaveBeenCalledTimes(2));
    expect(vi.mocked(executeSchool).mock.calls).toEqual([
      [9, 2],
      [9, 3],
    ]);
  });

  it("Undo is disabled with the reason when not allowed", async () => {
    vi.mocked(getRun).mockResolvedValue(detail([school(1, "completed")]));
    vi.mocked(getRunSchool).mockResolvedValue({
      ...school(1, "completed", {
        canUndo: false,
        undoBlockReason: "A slot was added in 2026-2027 after progression.",
      }),
      rowLog: { created: { child_class: 3 }, archived: { slot: 2 } },
    });

    await openRun();
    const row = await screen.findByTestId("detail-row-1");
    await userEvent.click(within(row).getByRole("button", { name: "Details" }));

    expect(await screen.findByRole("button", { name: "Undo" })).toBeDisabled();
    expect(
      screen.getByText("Undo unavailable: A slot was added in 2026-2027 after progression.")
    ).toBeInTheDocument();
    expect(screen.getByText("child class")).toBeInTheDocument();
    expect(screen.getByText("slot")).toBeInTheDocument();
  });

  it("Undo calls the endpoint when allowed", async () => {
    vi.mocked(getRun).mockResolvedValue(detail([school(1, "completed")]));
    vi.mocked(getRunSchool).mockResolvedValue({
      ...school(1, "completed", { canUndo: true }),
      rowLog: {},
    });
    vi.mocked(undoSchool).mockResolvedValue({ schoolId: 1, status: "undone", error: null });

    await openRun();
    await userEvent.click(
      within(await screen.findByTestId("detail-row-1")).getByRole("button", { name: "Details" })
    );
    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));
    // Undo asks for confirmation first: the school's name must be typed.
    expect(undoSchool).not.toHaveBeenCalled();
    const confirm = await screen.findByRole("button", { name: "Undo progression" });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Type to confirm"), "School 1");
    await userEvent.click(confirm);

    await waitFor(() => expect(undoSchool).toHaveBeenCalledWith(9, 1));
  });
});
