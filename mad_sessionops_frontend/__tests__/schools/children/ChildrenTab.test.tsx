import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChildrenTab } from "@/components/schools/children/ChildrenTab";
import type { SchoolClassItem } from "@/lib/api/services/structure.service";
import type { BucketItem } from "@/lib/api/services/buckets.service";
import type { ChildItem } from "@/lib/api/services/children.service";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/lib/api/services/structure.service", () => ({
  fetchSchoolClasses: vi.fn(),
}));

vi.mock("@/lib/api/services/buckets.service", () => ({
  fetchBuckets: vi.fn(),
}));

vi.mock("@/lib/api/services/children.service", () => ({
  fetchChildren: vi.fn(),
}));

vi.mock("@/lib/api/services/exports.service", () => ({
  exportSchoolChildren: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("react-hot-toast", () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

import { fetchSchoolClasses } from "@/lib/api/services/structure.service";
import { fetchBuckets } from "@/lib/api/services/buckets.service";
import { fetchChildren } from "@/lib/api/services/children.service";
import toast from "react-hot-toast";
import { exportSchoolChildren } from "@/lib/api/services/exports.service";

const MOCK_CLASS: SchoolClassItem = {
  schoolClassId: 1,
  gradeClassId: 5,
  className: "Grade 5",
  classCode: "G5",
  programName: "Foundation",
  sectionsCount: 0,
  sections: [],
};

const MOCK_BUCKET: BucketItem = {
  classSectionId: 10,
  sectionName: "group_1",
  sectionDisplayName: "Group 1",
  activeChildrenCount: 2,
};

function makeChild(id: number, firstName: string, section: ChildItem["currentSection"]): ChildItem {
  return {
    childId: id,
    firstName,
    lastName: "Test",
    gender: "other",
    age: 10,
    city: null,
    motherTongue: null,
    dateOfBirth: null,
    dateOfEnrollment: null,
    madJoiningDate: null,
    isActive: true,
    currentSchoolClass: { schoolClassId: 1, className: "Grade 5" },
    currentSection: section,
  };
}

describe("ChildrenTab — F-M6-7", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchSchoolClasses).mockResolvedValue([MOCK_CLASS]);
    vi.mocked(fetchBuckets).mockResolvedValue([MOCK_BUCKET]);
  });

  it("test_bucket_column_renders_display_name", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([
      makeChild(1, "Asha", {
        classSectionId: 10,
        sectionDisplayName: "Group 1",
        sectionName: "group_1",
      }),
    ]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);

    await waitFor(() => {
      expect(screen.getByText("Group 1")).toBeInTheDocument();
    });
  });

  it("test_bucket_column_renders_unassigned_chip", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([makeChild(1, "Kiran", null)]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);

    await waitFor(() => {
      expect(screen.getByText("Unassigned")).toBeInTheDocument();
    });
  });

  it("test_bucket_filter_dropdown_options_and_param_wiring", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([
      makeChild(1, "Asha", {
        classSectionId: 10,
        sectionDisplayName: "Group 1",
        sectionName: "group_1",
      }),
    ]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);

    await waitFor(() => expect(screen.getByText("Group 1")).toBeInTheDocument());

    // Open the bucket filter select and choose "Unassigned"
    const selects = screen.getAllByRole("combobox");
    const bucketSelect = selects[selects.length - 1];
    await userEvent.click(bucketSelect);
    await userEvent.click(await screen.findByRole("option", { name: "Unassigned" }));

    await waitFor(() => {
      const lastCall = vi.mocked(fetchChildren).mock.calls.at(-1);
      expect(lastCall?.[1]).toEqual(expect.objectContaining({ unassigned: true }));
    });
  });

  it("test_bucket_filter_specific_bucket_sends_section_id", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([
      makeChild(1, "Asha", {
        classSectionId: 10,
        sectionDisplayName: "Group 1",
        sectionName: "group_1",
      }),
    ]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);

    await waitFor(() => expect(screen.getByText("Group 1")).toBeInTheDocument());

    const selects = screen.getAllByRole("combobox");
    const bucketSelect = selects[selects.length - 1];
    await userEvent.click(bucketSelect);
    await userEvent.click(await screen.findByRole("option", { name: "Group 1" }));

    await waitFor(() => {
      const lastCall = vi.mocked(fetchChildren).mock.calls.at(-1);
      expect(lastCall?.[1]).toEqual(expect.objectContaining({ section_id: 10 }));
    });
  });

  it("test_status_tab_all_shows_active_and_inactive_children", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([
      makeChild(1, "Asha", null),
      { ...makeChild(2, "Kiran", null), isActive: false },
    ]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);

    await waitFor(() => expect(screen.getByText("Asha Test")).toBeInTheDocument());
    expect(screen.queryByText("Kiran Test")).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("All"));

    await waitFor(() => expect(screen.getByText("Kiran Test")).toBeInTheDocument());
    expect(screen.getByText("Asha Test")).toBeInTheDocument();
  });

  it("test_edit_icon_opens_drawer_and_close_button_dismisses_it", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([makeChild(1, "Asha", null)]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);

    await waitFor(() => expect(screen.getByText("Asha Test")).toBeInTheDocument());

    const row = screen.getByText("Asha Test").closest("tr")!;
    const rowButtons = within(row).getAllByRole("button");
    await userEvent.click(rowButtons[0]);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Edit Child")).toBeInTheDocument();

    await userEvent.click(within(dialog).getAllByRole("button")[0]);

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("test_deactivate_icon_opens_modal_and_close_button_dismisses_it", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([makeChild(1, "Asha", null)]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);

    await waitFor(() => expect(screen.getByText("Asha Test")).toBeInTheDocument());

    const row = screen.getByText("Asha Test").closest("tr")!;
    const rowButtons = within(row).getAllByRole("button");
    await userEvent.click(rowButtons[1]);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Deactivate child")).toBeInTheDocument();

    await userEvent.click(within(dialog).getAllByRole("button")[0]);

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("test_reactivate_icon_opens_modal_and_close_button_dismisses_it", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([
      { ...makeChild(1, "Kiran", null), isActive: false },
    ]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);

    await waitFor(() => expect(screen.getByPlaceholderText("Search by name…")).toBeInTheDocument());

    await userEvent.click(screen.getByText("Inactive"));

    await waitFor(() => expect(screen.getByText("Kiran Test")).toBeInTheDocument());

    const row = screen.getByText("Kiran Test").closest("tr")!;
    const rowButtons = within(row).getAllByRole("button");
    await userEvent.click(rowButtons[1]);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Reactivate child")).toBeInTheDocument();

    await userEvent.click(within(dialog).getAllByRole("button")[0]);

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("test_search_input_updates_and_clear_button_resets_it", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([makeChild(1, "Asha", null)]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);

    await waitFor(() => expect(screen.getByText("Asha Test")).toBeInTheDocument());

    const searchBox = screen.getByPlaceholderText("Search by name…");
    const baselineButtons = screen.getAllByRole("button").length;

    await userEvent.type(searchBox, "abc");
    expect(searchBox).toHaveValue("abc");

    await waitFor(() => expect(screen.getAllByRole("button").length).toBe(baselineButtons + 1));

    // Scope to the search field — header buttons (Export CSV, Enroll Child) shift global indexes.
    const clearButton = within(searchBox.closest(".MuiInputBase-root") as HTMLElement).getByRole(
      "button"
    );
    await userEvent.click(clearButton);

    expect(searchBox).toHaveValue("");
  });

  it("test_class_filter_selection_sends_class_id_and_updates_state", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([makeChild(1, "Asha", null)]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);

    await waitFor(() => expect(screen.getByText("Asha Test")).toBeInTheDocument());

    const selects = screen.getAllByRole("combobox");
    const classSelect = selects[0];
    await userEvent.click(classSelect);
    await userEvent.click(await screen.findByRole("option", { name: "Grade 5" }));

    await waitFor(() => {
      const lastCall = vi.mocked(fetchChildren).mock.calls.at(-1);
      expect(lastCall?.[1]).toEqual(expect.objectContaining({ class_id: 1 }));
    });
  });

  it("test_no_results_state_and_clear_filters_button_resets_search", async () => {
    vi.mocked(fetchChildren).mockImplementation(async (_schoolId, params) => {
      if (params?.search) return [];
      return [makeChild(1, "Asha", null)];
    });

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);

    await waitFor(() => expect(screen.getByText("Asha Test")).toBeInTheDocument());

    const searchBox = screen.getByPlaceholderText("Search by name…");
    await userEvent.type(searchBox, "zzz");

    await waitFor(() =>
      expect(screen.getByText("No children match the selected filters.")).toBeInTheDocument()
    );

    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(searchBox).toHaveValue("");
    await waitFor(() => expect(screen.getByText("Asha Test")).toBeInTheDocument());
  });

  it("test_empty_state_shown_when_no_children_and_enroll_button_opens_and_closes_modal", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);

    await waitFor(() =>
      expect(screen.getByText("Add children to start your school's journey")).toBeInTheDocument()
    );

    const enrollButtons = screen.getAllByRole("button", { name: "Enroll Child" });
    await userEvent.click(enrollButtons[0]);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeInTheDocument();

    await userEvent.click(within(dialog).getAllByRole("button")[0]);

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("test_load_error_state_shows_retry_and_calls_toast_error", async () => {
    vi.mocked(fetchChildren).mockRejectedValue(new Error("network down"));

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);

    await waitFor(() => expect(screen.getByText("Failed to load children.")).toBeInTheDocument());

    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(toast.error).toHaveBeenCalledWith("Could not load children");
  });

  it("test_empty_state_cta_button_opens_enroll_modal", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);

    await waitFor(() =>
      expect(screen.getByText("Add children to start your school's journey")).toBeInTheDocument()
    );

    const enrollButtons = screen.getAllByRole("button", { name: "Enroll Child" });
    expect(enrollButtons.length).toBeGreaterThan(1);
    await userEvent.click(enrollButtons[enrollButtons.length - 1]);

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("test_empty_state_hides_enroll_cta_when_canModify_is_false", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" canModify={false} />);

    await waitFor(() =>
      expect(
        screen.getByText("No children have been enrolled in this school yet.")
      ).toBeInTheDocument()
    );

    expect(screen.queryByRole("button", { name: "Enroll Child" })).not.toBeInTheDocument();
  });

  // ── F-M9-2 Export CSV ────────────────────────────────────────────────────────

  it("test_export_button_sends_current_filters", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([
      makeChild(1, "Asha", null),
      { ...makeChild(2, "Kiran", null), isActive: false },
    ]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);
    await waitFor(() => expect(screen.getByText("Asha Test")).toBeInTheDocument());

    // Bucket filter → Unassigned, status tab → All
    const selects = screen.getAllByRole("combobox");
    await userEvent.click(selects[selects.length - 1]);
    await userEvent.click(await screen.findByRole("option", { name: "Unassigned" }));
    await userEvent.click(screen.getByText("All"));

    const exportButton = screen.getByRole("button", { name: /export csv/i });
    await waitFor(() => expect(exportButton).not.toBeDisabled());
    await userEvent.click(exportButton);

    await waitFor(() =>
      expect(exportSchoolChildren).toHaveBeenCalledWith(580, {
        status: "all",
        search: "",
        classId: null,
        sectionId: null,
        unassigned: true,
      })
    );
  });

  it("test_export_button_sends_specific_bucket_as_section_id", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([
      makeChild(1, "Asha", {
        classSectionId: 10,
        sectionDisplayName: "Group 1",
        sectionName: "group_1",
      }),
    ]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" />);
    await waitFor(() => expect(screen.getByText("Asha Test")).toBeInTheDocument());

    const selects = screen.getAllByRole("combobox");
    await userEvent.click(selects[selects.length - 1]);
    await userEvent.click(await screen.findByRole("option", { name: "Group 1" }));

    const exportButton = screen.getByRole("button", { name: /export csv/i });
    await waitFor(() => expect(exportButton).not.toBeDisabled());
    await userEvent.click(exportButton);

    await waitFor(() =>
      expect(exportSchoolChildren).toHaveBeenCalledWith(
        580,
        expect.objectContaining({ status: "active", sectionId: 10, unassigned: false })
      )
    );
  });

  it("test_export_button_visible_without_modify_permission", async () => {
    vi.mocked(fetchChildren).mockResolvedValue([makeChild(1, "Asha", null)]);

    render(<ChildrenTab schoolId={580} activeYear="2026-2027" canModify={false} />);

    await waitFor(() => expect(screen.getByText("Asha Test")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /export csv/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enroll Child" })).not.toBeInTheDocument();
  });
});
