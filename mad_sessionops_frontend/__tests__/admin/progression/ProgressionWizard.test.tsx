import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProgressionWizard } from "@/components/admin/progression/ProgressionWizard";
import type { PrecheckResult, PreviewResult } from "@/lib/api/services/progression.service";

vi.mock("@/lib/api/services/progression.service", () => ({
  fetchEligibleSchools: vi.fn(),
  precheckSchools: vi.fn(),
  previewSchools: vi.fn(),
  fetchPreviewChildren: vi.fn().mockResolvedValue({ total: 0, page: 1, pageSize: 50, results: [] }),
  startRun: vi.fn(),
  executeSchool: vi.fn(),
  releaseSchool: vi.fn(),
}));
vi.mock("@/lib/api/services/catalog.service", () => ({
  fetchAdminClasses: vi.fn().mockResolvedValue([
    { classId: 5, className: "5th" },
    { classId: 8, className: "8th" },
  ]),
}));
vi.mock("@/lib/toast/toast", () => ({ showApiError: vi.fn(), showSuccess: vi.fn() }));

import {
  executeSchool,
  fetchEligibleSchools,
  precheckSchools,
  previewSchools,
  startRun,
} from "@/lib/api/services/progression.service";

const SCHOOLS = [
  {
    schoolId: 1,
    schoolName: "Alpha",
    city: "Pune",
    currentYearLabel: "2025-2026",
    targetYearLabel: "2026-2027",
    yearsBehind: 1,
    eligible: true,
    reason: null,
    reasonMessage: null,
  },
  {
    schoolId: 2,
    schoolName: "Bravo",
    city: "Delhi",
    currentYearLabel: "2026-2027",
    targetYearLabel: "2027-2028",
    yearsBehind: 0,
    eligible: true,
    reason: null,
    reasonMessage: null,
  },
  {
    schoolId: 3,
    schoolName: "Done",
    city: "Pune",
    currentYearLabel: "2026-2027",
    targetYearLabel: "2027-2028",
    yearsBehind: 0,
    eligible: false,
    reason: "ALREADY_IN_RUN",
    reasonMessage: "The school is already in an unfinished progression run.",
  },
];

function pre(id: number, name: string, status: PrecheckResult["status"]): PrecheckResult {
  return {
    schoolId: id,
    schoolName: name,
    currentYearLabel: id === 1 ? "2025-2026" : "2026-2027",
    targetYearLabel: id === 1 ? "2026-2027" : "2027-2028",
    status,
    blockers:
      status === "blocked"
        ? [{ code: "CHILD_CLASS_CONFLICT", message: "2 child(ren) have no class." }]
        : [],
    warnings: [],
  };
}

function prev(id: number, name: string, graduating = 0): PreviewResult {
  return {
    ...pre(id, name, "ready"),
    counts: {
      schoolClassesCopied: 4,
      schoolClassesAdded: [],
      sectionsCopied: 2,
      childrenMoving: [{ from: "5th", to: "6th", n: 3 }],
      childrenStaying: [{ class: "8th", n: 2 }],
      childrenGraduating: graduating,
      volunteersCarried: 1,
      archiveCounts: { slot: 2 },
    },
  };
}

async function selectAndPrecheck(name = "Alpha") {
  render(<ProgressionWizard />);
  await screen.findByText("Alpha");
  await userEvent.click(screen.getByRole("radio", { name: `Select ${name}` }));
  await userEvent.click(screen.getByRole("button", { name: "Next" }));
}

const RUN = {
  status: "in_progress" as const,
  yearMoves: [{ label: "2025-2026 → 2026-2027", schools: 1 }],
  startedByName: "Admin",
  startedAt: "2026-09-30T10:00:00Z",
  finishedAt: null,
  cleanup: {},
  schoolCounts: { queued: 1 },
};

describe("ProgressionWizard — F-M10-9 (one school per run)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchEligibleSchools).mockResolvedValue({
      activeYearLabel: "2026-2027",
      schools: SCHOOLS,
    });
    vi.mocked(precheckSchools).mockImplementation(async (ids) =>
      ids.map((id) => (id === 2 ? pre(2, "Bravo", "blocked") : pre(1, "Alpha", "ready")))
    );
    vi.mocked(previewSchools).mockImplementation(async (schools) =>
      schools.map((s) => prev(s.schoolId, "Alpha", s.graduateClassIds.length ? 2 : 0))
    );
  });

  it("step 1: each school shows its own move; years behind are flagged", async () => {
    render(<ProgressionWizard />);
    const alpha = await screen.findByTestId("school-row-1");
    expect(within(alpha).getByText("2026-2027")).toBeInTheDocument(); // moves to
    expect(within(alpha).getByText("1 yr behind")).toBeInTheDocument();
    const bravo = screen.getByTestId("school-row-2");
    expect(within(bravo).getByText("2027-2028")).toBeInTheDocument();
    // Schools are on two different years → a year filter appears.
    expect(screen.getByRole("tab", { name: /All years/ })).toBeInTheDocument();
  });

  it("step 1: only one school can be chosen; picking another replaces it", async () => {
    render(<ProgressionWizard />);
    await screen.findByText("Alpha");
    expect(screen.queryByRole("checkbox", { name: /Select all/ })).toBeNull();

    await userEvent.click(screen.getByRole("radio", { name: "Select Alpha" }));
    await userEvent.click(screen.getByRole("radio", { name: "Select Bravo" }));

    expect(screen.getByRole("radio", { name: "Select Alpha" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "Select Bravo" })).toBeChecked();
    expect(screen.getByText("Selected: Bravo")).toBeInTheDocument();
  });

  it("warns when the chosen school will make a newer year active", async () => {
    render(<ProgressionWizard />);
    await screen.findByText("Alpha");
    await userEvent.click(screen.getByRole("radio", { name: "Select Alpha" }));
    expect(screen.queryByText(/active academic year for the whole platform/)).toBeNull();

    await userEvent.click(screen.getByRole("radio", { name: "Select Bravo" }));
    expect(screen.getByText(/active academic year for the whole platform/)).toHaveTextContent(
      "2027-2028"
    );
  });

  it("step 1: shows only movable schools by default; ineligible ones can't be chosen", async () => {
    render(<ProgressionWizard />);
    await screen.findByText("Alpha");
    expect(screen.queryByText("Done")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: /All converted/ }));
    expect(screen.getByRole("radio", { name: "Select Done" })).toBeDisabled();
    expect(
      screen.getByText("The school is already in an unfinished progression run.")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("step 2: a blocked school shows its blockers and can't continue", async () => {
    await selectAndPrecheck("Bravo");

    expect(await screen.findByTestId("precheck-summary")).toHaveTextContent(
      "0 ready · 0 warning · 1 blocked"
    );
    expect(precheckSchools).toHaveBeenCalledWith([2]);

    const rows = screen.getAllByRole("row");
    const bravo = rows.find((r) => within(r).queryByText("Bravo"))!;
    await userEvent.click(within(bravo).getByRole("button", { name: "Details" }));
    const panel = await screen.findByRole("presentation");
    expect(within(panel).getByText("2 child(ren) have no class.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Close details" }));

    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("step 3 → 4: graduation marks go into Start for the one school, then it runs", async () => {
    vi.mocked(startRun).mockResolvedValue({ runId: 42, ...RUN });
    vi.mocked(executeSchool).mockResolvedValueOnce({
      schoolId: 1,
      status: "failed",
      error: "boom",
    });

    await selectAndPrecheck();
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));

    const row = await screen.findByTestId("preview-row-1");
    await userEvent.click(within(row).getByRole("button", { name: "Details" }));
    await userEvent.click(await screen.findByLabelText("All of 8th"));
    await waitFor(() =>
      expect(previewSchools).toHaveBeenLastCalledWith([
        { schoolId: 1, graduateClassIds: [8], graduateChildIds: [] },
      ])
    );
    await userEvent.click(screen.getByRole("button", { name: "Close details" }));

    await userEvent.click(screen.getByRole("button", { name: "Run progression" }));
    // Start stays disabled until the admin types the school's name.
    const start = await screen.findByRole("button", { name: "Start" });
    expect(start).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Type to confirm"), "alpha");
    await userEvent.click(start);

    expect(startRun).toHaveBeenCalledWith([
      { schoolId: 1, graduateClassIds: [8], graduateChildIds: [] },
    ]);
    await waitFor(() => expect(executeSchool).toHaveBeenCalledTimes(1));
    expect(vi.mocked(executeSchool).mock.calls).toEqual([[42, 1]]);
    const failed = await screen.findByTestId("run-row-1");
    expect(within(failed).getByText("boom")).toBeInTheDocument();
    // Retry/Release appear once the loop has finished.
    expect(await within(failed).findByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(within(failed).getByRole("button", { name: "Release" })).toBeInTheDocument();
  });

  it("a network error stops the run and points to Resume", async () => {
    vi.mocked(startRun).mockResolvedValue({ runId: 43, ...RUN });
    vi.mocked(executeSchool).mockRejectedValueOnce({
      code: "NETWORK_ERROR",
      message: "Network error.",
    });

    await selectAndPrecheck();
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));
    await screen.findByTestId("preview-row-1");
    await userEvent.click(screen.getByRole("button", { name: "Run progression" }));
    await userEvent.type(await screen.findByLabelText("Type to confirm"), "Alpha");
    await userEvent.click(screen.getByRole("button", { name: "Start" }));

    expect(await screen.findByText(/Resume from the Runs tab/)).toBeInTheDocument();
    expect(executeSchool).toHaveBeenCalledTimes(1);
  });
});
