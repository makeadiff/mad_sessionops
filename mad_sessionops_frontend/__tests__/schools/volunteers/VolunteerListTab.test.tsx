import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { VolunteerListTab } from "@/components/schools/volunteers/VolunteerListTab";
import type { VolunteerListResponse } from "@/lib/api/services/volunteers.service";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/lib/api/services/volunteers.service", () => ({
  fetchVolunteers: vi.fn(),
}));

vi.mock("@/lib/api/services/exports.service", () => ({
  exportSchoolVolunteers: vi.fn().mockResolvedValue(undefined),
}));

import { fetchVolunteers } from "@/lib/api/services/volunteers.service";
import { exportSchoolVolunteers } from "@/lib/api/services/exports.service";

function makeResponse(overrides: Partial<VolunteerListResponse> = {}): VolunteerListResponse {
  return {
    status: "ok",
    message: null,
    volunteers: [],
    ...overrides,
  };
}

describe("VolunteerListTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("test_loading_skeleton_shown_before_data_resolves", async () => {
    let resolvePromise: (value: VolunteerListResponse) => void = () => {};
    vi.mocked(fetchVolunteers).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePromise = resolve;
        })
    );

    render(<VolunteerListTab schoolId={580} />);

    expect(document.querySelectorAll(".MuiSkeleton-root").length).toBeGreaterThan(0);

    resolvePromise(makeResponse());
    await waitFor(() => expect(document.querySelectorAll(".MuiSkeleton-root").length).toBe(0));
  });

  it("test_error_state_shown_when_fetch_rejects", async () => {
    vi.mocked(fetchVolunteers).mockRejectedValue(new Error("network down"));

    render(<VolunteerListTab schoolId={580} />);

    await waitFor(() => expect(screen.getByText("Could not load volunteers")).toBeInTheDocument());
    expect(screen.getByText("Failed to load volunteers. Please try again.")).toBeInTheDocument();
  });

  it("test_no_worknode_rich_empty_state_renders_badge_heading_subtitle_and_bullets", async () => {
    vi.mocked(fetchVolunteers).mockResolvedValue(
      makeResponse({ status: "no_worknode", volunteers: [] })
    );

    render(<VolunteerListTab schoolId={580} />);

    await waitFor(() => expect(screen.getByText("No Worknode configured")).toBeInTheDocument());
    expect(screen.getByText("Setup required")).toBeInTheDocument();
    expect(
      screen.getByText(
        "No Worknode found for this school. Contact an admin to map it in Platform Commons before volunteers can be assigned here."
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText("A Worknode links this school to volunteers tagged in Platform Commons")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Once mapped, tagged volunteers appear here automatically")
    ).toBeInTheDocument();
  });

  it("test_no_worknode_uses_backend_message_when_present", async () => {
    vi.mocked(fetchVolunteers).mockResolvedValue(
      makeResponse({ status: "no_worknode", message: "Custom worknode message", volunteers: [] })
    );

    render(<VolunteerListTab schoolId={580} />);

    await waitFor(() => expect(screen.getByText("Custom worknode message")).toBeInTheDocument());
  });

  it("test_no_volunteers_rich_empty_state_renders_badge_heading_subtitle_and_bullets", async () => {
    vi.mocked(fetchVolunteers).mockResolvedValue(
      makeResponse({ status: "no_volunteers", volunteers: [] })
    );

    render(<VolunteerListTab schoolId={580} />);

    await waitFor(() => expect(screen.getByText("No volunteers found")).toBeInTheDocument());
    expect(screen.getByText("Get started")).toBeInTheDocument();
    expect(
      screen.getByText("Add this school as the volunteer's workplace in Platform Commons")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Assign them to teaching slots and mentoring circles once they appear")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Every volunteer mapped means one more class can run")
    ).toBeInTheDocument();
  });

  it("test_populated_list_renders_volunteer_cards_and_count_badge", async () => {
    vi.mocked(fetchVolunteers).mockResolvedValue(
      makeResponse({
        status: "ok",
        volunteers: [
          {
            userId: 1,
            userDisplayName: "Asha Kumar",
            userLogin: "asha.kumar",
            userRole: "Wingman",
            email: "asha@example.com",
            contact: "9999999999",
            city: "Pune",
            state: "MH",
            activeSlotClassCount: 2,
            activeSlotClassSectionId: null,
          },
          {
            userId: 2,
            userDisplayName: "Ravi Singh",
            userLogin: "ravi.singh",
            userRole: "Volunteer",
            email: "ravi@example.com",
            contact: null,
            city: null,
            state: null,
            activeSlotClassCount: 0,
            activeSlotClassSectionId: null,
          },
        ],
      })
    );

    render(<VolunteerListTab schoolId={580} />);

    await waitFor(() => expect(screen.getByText("Asha Kumar")).toBeInTheDocument());
    expect(screen.getByText("Ravi Singh")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("2 classes")).toBeInTheDocument();
    expect(screen.getByText("Not teaching")).toBeInTheDocument();
  });

  it("test_clicking_card_opens_detail_drawer_and_close_dismisses_it", async () => {
    vi.mocked(fetchVolunteers).mockResolvedValue(
      makeResponse({
        status: "ok",
        volunteers: [
          {
            userId: 1,
            userDisplayName: "Asha Kumar",
            userLogin: "asha.kumar",
            userRole: "Wingman",
            email: "asha@example.com",
            contact: "9999999999",
            city: "Pune",
            state: "MH",
            activeSlotClassCount: 2,
            activeSlotClassSectionId: null,
          },
        ],
      })
    );

    render(<VolunteerListTab schoolId={580} />);

    await waitFor(() => expect(screen.getByText("Asha Kumar")).toBeInTheDocument());

    await userEvent.click(screen.getByText("Asha Kumar"));

    expect(await screen.findByText("asha@example.com")).toBeInTheDocument();
    expect(screen.getByText("Teaching 2 classes")).toBeInTheDocument();

    const closeButton = screen.getByRole("button");
    await userEvent.click(closeButton);

    await waitFor(() => expect(screen.queryByText("asha@example.com")).not.toBeInTheDocument());
  });

  // ── F-M9-3 Export CSV ────────────────────────────────────────────────────────

  it("test_export_button_in_populated_state_calls_export", async () => {
    vi.mocked(fetchVolunteers).mockResolvedValue(
      makeResponse({
        status: "ok",
        volunteers: [
          {
            userId: 1,
            userDisplayName: "Asha Kumar",
            userLogin: "asha.kumar",
            userRole: "Wingman",
            email: "asha@example.com",
            contact: null,
            city: null,
            state: null,
            activeSlotClassCount: 0,
            activeSlotClassSectionId: null,
          },
        ],
      })
    );

    render(<VolunteerListTab schoolId={580} />);
    await waitFor(() => expect(screen.getByText("Asha Kumar")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: /export csv/i }));

    await waitFor(() => expect(exportSchoolVolunteers).toHaveBeenCalledWith(580));
  });

  it.each(["no_worknode", "no_volunteers"] as const)(
    "test_export_button_hidden_in_%s_state",
    async (status) => {
      vi.mocked(fetchVolunteers).mockResolvedValue(makeResponse({ status, message: "x" }));

      render(<VolunteerListTab schoolId={580} />);

      await waitFor(() => expect(screen.queryByRole("progressbar")).not.toBeInTheDocument());
      await waitFor(() =>
        expect(screen.queryByRole("button", { name: /export csv/i })).not.toBeInTheDocument()
      );
    }
  );
});
