import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api/client", () => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));
vi.mock("@/lib/redux/hooks", () => ({
  useAppSelector: () => ({ role: "Project Lead", name: "Admin" }),
}));
vi.mock("@/lib/toast/toast", () => ({ showApiError: vi.fn(), showSuccess: vi.fn() }));

import { api } from "@/lib/api/client";
import { AcademicYearsPage, nextYearLabel } from "@/components/admin/AcademicYearsPage";

const YEARS = [
  { academic_year_id: 8, label: "2027-2028", is_active: false, school_count: 0, can_remove: true },
  { academic_year_id: 7, label: "2026-2027", is_active: true, school_count: 63, can_remove: false },
];

describe("AcademicYearsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockResolvedValue(YEARS);
  });

  it("shows usage, the Next year, and Remove only for an unused inactive year", async () => {
    render(<AcademicYearsPage />);

    expect(await screen.findByText("Used by 63 schools")).toBeInTheDocument();
    expect(screen.getByText("Not used by any school yet")).toBeInTheDocument();
    expect(await screen.findByText("Next")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove 2027-2028" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove 2026-2027" })).not.toBeInTheDocument();
    expect(screen.getByText(/There is no manual switch/)).toBeInTheDocument();
  });

  it("Remove asks for confirmation, then deletes and reloads", async () => {
    vi.mocked(api.delete).mockResolvedValue(undefined);
    render(<AcademicYearsPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Remove 2027-2028" }));
    expect(api.delete).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove" }));

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/academic-years/admin/8/"));
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  });

  it("Create is prefilled with the year after the latest", async () => {
    render(<AcademicYearsPage />);
    await screen.findByText("2026-2027");

    await userEvent.click(screen.getByRole("button", { name: "Create Year" }));

    expect(await screen.findByLabelText("Label")).toHaveValue("2028-2029");
  });

  it("rejects the short label format before calling the server", async () => {
    render(<AcademicYearsPage />);
    await screen.findByText("2026-2027");
    await userEvent.click(screen.getByRole("button", { name: "Create Year" }));

    const input = await screen.findByLabelText("Label");
    await userEvent.clear(input);
    await userEvent.type(input, "2028-29");

    expect(screen.getByText(/Use the full format/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("nextYearLabel picks the year after the latest", () => {
    expect(nextYearLabel([{ label: "2025-2026" }, { label: "2026-2027" }])).toBe("2027-2028");
  });
});
