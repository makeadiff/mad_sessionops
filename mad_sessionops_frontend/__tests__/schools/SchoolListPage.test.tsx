import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { SchoolListPage } from "@/components/schools/SchoolListPage";
import authReducer from "@/lib/redux/features/auth/authSlice";

function makeStore(preloadedState?: object) {
  return configureStore({ reducer: { auth: authReducer }, preloadedState });
}

function renderWithProvider(ui: React.ReactElement, preloadedState?: object) {
  const store = makeStore(preloadedState);
  return render(<Provider store={store}>{ui}</Provider>);
}

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockRouterPush = vi.fn();

vi.mock("@/lib/api/services/schools.service", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/services/schools.service")>();
  return { ...actual, fetchSchools: vi.fn() };
});

vi.mock("@/lib/api/services/exports.service", () => ({
  exportSchoolsSummary: vi.fn().mockResolvedValue(undefined),
  exportAllChildren: vi.fn().mockResolvedValue(undefined),
  exportAllVolunteers: vi.fn().mockResolvedValue(undefined),
  exportGapReport: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockRouterPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/schools",
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

import { fetchSchools } from "@/lib/api/services/schools.service";
import {
  exportAllChildren,
  exportAllVolunteers,
  exportGapReport,
  exportSchoolsSummary,
} from "@/lib/api/services/exports.service";

const MOCK_SUMMARY = {
  totalSchools: 2,
  fullyConfigured: 0,
  childrenEnrolled: 45,
  activeVolunteers: 12,
  academicYear: "2025-26",
};

const MOCK_SCHOOLS = [
  {
    partnerId: 580,
    name: "Govt. High School Shaikpet",
    initials: "GH",
    city: "Hyderabad",
    contactPersonName: "Ramesh Kumar",
    contactPhone: "9876543210",
    coName: "Ipshita Das",
    setupStatus: "not_configured" as const,
    classesCount: 3,
    childrenCount: 25,
    volunteersCount: 5,
    assignmentsCount: 10,
    academicYearLabel: "2026-2027",
    updatedAt: "2026-04-29T10:00:00Z",
  },
  {
    partnerId: 612,
    name: "Municipal School Jubilee Hills",
    initials: "MS",
    city: "Hyderabad",
    contactPersonName: null,
    contactPhone: null,
    coName: "Ipshita Das",
    setupStatus: "not_configured" as const,
    classesCount: 0,
    childrenCount: 20,
    volunteersCount: 7,
    assignmentsCount: 0,
    academicYearLabel: "2026-2027",
    updatedAt: "2026-04-28T08:00:00Z",
  },
];

// ── Tests — F-M1-4 ───────────────────────────────────────────────────────────

describe("SchoolListPage — F-M1-4", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRouterPush.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("test_schools_page_renders_table_with_data", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);

    await waitFor(() => {
      expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
    });

    expect(screen.getByText("Municipal School Jubilee Hills")).toBeInTheDocument();

    // Column headers visible
    expect(screen.getByText("School")).toBeInTheDocument();
    expect(screen.getByText("City")).toBeInTheDocument();
    expect(screen.getByText("Children")).toBeInTheDocument();
  });

  it("test_schools_page_shows_empty_state_for_cho", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: [],
      summary: { ...MOCK_SUMMARY, totalSchools: 0 },
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Test CHO" />);

    await waitFor(() => {
      expect(screen.getByText("No schools assigned yet")).toBeInTheDocument();
    });

    // Toolbar and table headers are NOT rendered for empty state
    expect(screen.queryByText("School")).not.toBeInTheDocument();
  });

  it("test_schools_page_shows_scope_warning_message_for_cho_with_no_worknode_mapping", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: [],
      summary: { ...MOCK_SUMMARY, totalSchools: 0 },
      scopeWarning: {
        code: "no_worknode_mapping",
        message:
          "You are not assigned to any schools or partner. Please contact your community organizer or admin.",
      },
    });

    renderWithProvider(<SchoolListPage userName="Test CHO" />);

    await waitFor(() => {
      expect(
        screen.getByText(
          "You are not assigned to any schools or partner. Please contact your community organizer or admin."
        )
      ).toBeInTheDocument();
    });

    // The scope-warning message replaces the generic empty-state copy
    expect(screen.queryByText("No schools assigned yet")).not.toBeInTheDocument();
    expect(screen.getByText("No schools assigned")).toBeInTheDocument();
  });

  it("test_schools_page_scope_warning_survives_without_redux_login_state", async () => {
    // Simulates a page refresh: redux's login-time scopeWarning is gone,
    // but the schools list endpoint still returns the fresh scope_warning.
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: [],
      summary: { ...MOCK_SUMMARY, totalSchools: 0 },
      scopeWarning: {
        code: "no_worknode_mapping",
        message:
          "You are not assigned to any schools or partner. Please contact your community organizer or admin.",
      },
    });

    renderWithProvider(<SchoolListPage userName="Test CHO" />, {
      auth: { scopeWarning: null },
    });

    await waitFor(() => {
      expect(
        screen.getByText(
          "You are not assigned to any schools or partner. Please contact your community organizer or admin."
        )
      ).toBeInTheDocument();
    });
  });

  it("test_schools_page_search_debounces_calls", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);

    await waitFor(() => {
      expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/search by school name/i);
    await userEvent.type(searchInput, "Shaikpet");

    // After debounce settles (200ms), only the matching school remains
    await waitFor(
      () => {
        expect(screen.queryByText("Municipal School Jubilee Hills")).not.toBeInTheDocument();
      },
      { timeout: 1000 }
    );

    expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();

    // fetchSchools was called only once on mount — search is local, not per-keystroke
    expect(vi.mocked(fetchSchools)).toHaveBeenCalledTimes(1);
  });

  it("test_schools_page_shows_error_on_fetch_failure", async () => {
    vi.mocked(fetchSchools).mockRejectedValue(new Error("network down"));

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);

    await waitFor(() => {
      expect(screen.getByText("Could not load schools. Please try again.")).toBeInTheDocument();
    });
  });

  it("test_schools_page_sort_by_name", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);
    await waitFor(() => {
      expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText(/Sort: Recently updated/));
    await userEvent.click(screen.getByText("Name (A–Z)"));

    const rows = screen.getAllByRole("row").filter((r) => r.getAttribute("tabindex") === "0");
    expect(rows[0]?.textContent).toContain("Govt. High School Shaikpet");
  });

  it("test_schools_page_sort_by_city", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);
    await waitFor(() => {
      expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText(/Sort: Recently updated/));
    await userEvent.click(screen.getByText("City (A–Z)"));

    expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
  });

  it("test_schools_page_sort_by_children_count", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);
    await waitFor(() => {
      expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText(/Sort: Recently updated/));
    await userEvent.click(screen.getByText("Most children"));

    const rows = screen.getAllByRole("row").filter((r) => r.getAttribute("tabindex") === "0");
    // Shaikpet has 25 children vs Jubilee Hills' 20 — should sort first
    expect(rows[0]?.textContent).toContain("Govt. High School Shaikpet");
  });

  it("test_schools_page_sort_by_clicking_children_column_header", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);
    await waitFor(() => {
      expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
    });

    // Numeric columns default to descending on first click — Shaikpet (25
    // children) should sort above Jubilee Hills (20).
    await userEvent.click(screen.getByText("Children"));

    const rows = screen.getAllByRole("row").filter((r) => r.getAttribute("tabindex") === "0");
    expect(rows[0]?.textContent).toContain("Govt. High School Shaikpet");

    // Clicking the same header again reverses the direction.
    await userEvent.click(screen.getByText("Children"));

    const rowsAfterToggle = screen
      .getAllByRole("row")
      .filter((r) => r.getAttribute("tabindex") === "0");
    expect(rowsAfterToggle[0]?.textContent).toContain("Municipal School Jubilee Hills");
  });

  it("test_schools_page_sort_by_clicking_school_column_header", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);
    await waitFor(() => {
      expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
    });

    // Text columns default to ascending (A–Z) on first click.
    await userEvent.click(screen.getByText("School"));

    const rows = screen.getAllByRole("row").filter((r) => r.getAttribute("tabindex") === "0");
    expect(rows[0]?.textContent).toContain("Govt. High School Shaikpet");
  });

  it("test_schools_page_clear_search_resets_filter", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);
    await waitFor(() => {
      expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/search by school name/i);
    await userEvent.type(searchInput, "nonexistent-school-xyz");

    await waitFor(() => {
      expect(screen.getByText("Clear search")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText("Clear search"));

    await waitFor(() => {
      expect(searchInput).toHaveValue("");
    });
    expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
  });

  it("test_schools_page_row_click_navigates_to_detail", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);

    await waitFor(() => {
      expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
    });

    // Click the first school row
    const row = screen.getByText("Govt. High School Shaikpet").closest('[role="row"]');
    expect(row).not.toBeNull();
    await userEvent.click(row!);

    expect(mockRouterPush).toHaveBeenCalledWith("/schools/580");
  });

  it("test_schools_page_row_enter_key_navigates_to_detail", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);

    await waitFor(() => {
      expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
    });

    const row = screen
      .getByText("Govt. High School Shaikpet")
      .closest('[role="row"]') as HTMLElement;
    row.focus();
    await userEvent.keyboard("{Enter}");

    expect(mockRouterPush).toHaveBeenCalledWith("/schools/580");
  });

  it("test_schools_page_row_space_key_navigates_to_detail", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);

    await waitFor(() => {
      expect(screen.getByText("Municipal School Jubilee Hills")).toBeInTheDocument();
    });

    const row = screen
      .getByText("Municipal School Jubilee Hills")
      .closest('[role="row"]') as HTMLElement;
    row.focus();
    await userEvent.keyboard(" ");

    expect(mockRouterPush).toHaveBeenCalledWith("/schools/612");
  });

  // ── F-M9-5 Export ────────────────────────────────────────────────────────────

  it("test_schools_export_passes_debounced_search", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);
    await waitFor(() => {
      expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
    });

    await userEvent.type(screen.getByPlaceholderText(/search by school name/i), "Shaikpet");
    await waitFor(
      () => {
        expect(screen.queryByText("Municipal School Jubilee Hills")).not.toBeInTheDocument();
      },
      { timeout: 1000 }
    );

    // Two or more options → the Export button opens a menu.
    await userEvent.click(screen.getByRole("button", { name: /^export$/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Schools summary" }));

    await waitFor(() => expect(exportSchoolsSummary).toHaveBeenCalledWith("Shaikpet"));
  });

  it("test_schools_export_menu_all_children", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);
    await waitFor(() => {
      expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: /^export$/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "All children" }));

    await waitFor(() => expect(exportAllChildren).toHaveBeenCalledWith(""));
    expect(exportSchoolsSummary).not.toHaveBeenCalled();
  });

  it("test_schools_export_menu_all_volunteers", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);
    await waitFor(() => {
      expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: /^export$/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "All volunteers" }));

    await waitFor(() => expect(exportAllVolunteers).toHaveBeenCalledWith(""));
  });

  it("test_schools_export_menu_lists_all_exports_and_runs_gap_report", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);
    await waitFor(() => {
      expect(screen.getByText("Govt. High School Shaikpet")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: /^export$/i }));
    const items = await screen.findAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual([
      "Schools summary",
      "All children",
      "All volunteers",
      "Gap report",
    ]);

    await userEvent.click(screen.getByRole("menuitem", { name: "Gap report" }));

    await waitFor(() => expect(exportGapReport).toHaveBeenCalledWith(""));
  });

  // ── M10 F-M10-5 progression banner ───────────────────────────────────────────

  it("test_progressing_banner_shows_count_and_dismisses", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
      progressingCount: 2,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);

    expect(
      await screen.findByText(/2 of your schools are being moved to the next academic year/)
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /close/i }));
    await waitFor(() =>
      expect(screen.queryByText(/being moved to the next academic year/)).not.toBeInTheDocument()
    );
  });

  it("test_no_progressing_banner_when_count_zero", async () => {
    vi.mocked(fetchSchools).mockResolvedValue({
      schools: MOCK_SCHOOLS,
      summary: MOCK_SUMMARY,
      scopeWarning: null,
      progressingCount: 0,
    });

    renderWithProvider(<SchoolListPage userName="Ipshita Das" />);

    await screen.findByText("Govt. High School Shaikpet");
    expect(screen.queryByText(/being moved to the next academic year/)).not.toBeInTheDocument();
  });
});
