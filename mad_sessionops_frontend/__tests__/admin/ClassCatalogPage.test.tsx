import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ClassCatalogPage } from "@/components/admin/ClassCatalogPage";
import type { AdminClass } from "@/lib/api/services/catalog.service";

vi.mock("@/lib/api/services/catalog.service", () => ({
  fetchAdminClasses: vi.fn(),
  createClass: vi.fn(),
  updateClass: vi.fn(),
}));

vi.mock("@/lib/toast/toast", () => ({
  showApiError: vi.fn(),
  showSuccess: vi.fn(),
}));

import { createClass, fetchAdminClasses, updateClass } from "@/lib/api/services/catalog.service";
import { showApiError } from "@/lib/toast/toast";

function cls(id: number, code: string, extra: Partial<AdminClass> = {}): AdminClass {
  return {
    classId: id,
    classCode: code,
    className: `${code}th`,
    sequence: Number(code),
    nextClassId: null,
    nextClassName: null,
    openForEnrolment: true,
    isActive: true,
    inUseCount: 0,
    ...extra,
  };
}

const CATALOG: AdminClass[] = [
  cls(1, "5", { nextClassId: 2, nextClassName: "6th", inUseCount: 3 }),
  cls(2, "6", { nextClassId: 3, nextClassName: "7th" }),
  cls(3, "7", { nextClassId: 4, nextClassName: "8th" }),
  cls(4, "8", { openForEnrolment: false }),
];

describe("ClassCatalogPage — F-M10-1", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchAdminClasses).mockResolvedValue(CATALOG);
  });

  it("renders the catalog in order with next class and enrolment state", async () => {
    render(<ClassCatalogPage />);

    const row5 = await screen.findByTestId("class-row-5");
    expect(within(row5).getByText("6th")).toBeInTheDocument();
    const row8 = screen.getByTestId("class-row-8");
    expect(within(row8).getByText("None — children stay")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Open 8th for enrolment" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Open 5th for enrolment" })).toBeChecked();
  });

  it("toggling enrolment PATCHes and reloads", async () => {
    vi.mocked(updateClass).mockResolvedValue({ ...CATALOG[3], openForEnrolment: true });
    render(<ClassCatalogPage />);

    await userEvent.click(await screen.findByRole("checkbox", { name: "Open 8th for enrolment" }));

    await waitFor(() => expect(updateClass).toHaveBeenCalledWith(4, { openForEnrolment: true }));
    expect(fetchAdminClasses).toHaveBeenCalledTimes(2);
  });

  it("shows an error toast when a toggle fails", async () => {
    vi.mocked(updateClass).mockRejectedValue({ code: "VALIDATION_ERROR", message: "nope" });
    render(<ClassCatalogPage />);

    await userEvent.click(await screen.findByRole("checkbox", { name: "Open 8th for enrolment" }));

    await waitFor(() => expect(showApiError).toHaveBeenCalled());
  });

  it("add class: validates shape, then creates with the next order number", async () => {
    vi.mocked(createClass).mockResolvedValue(cls(5, "9"));
    render(<ClassCatalogPage />);
    await screen.findByTestId("class-row-5");

    await userEvent.click(screen.getByRole("button", { name: "Add class" }));
    const dialog = await screen.findByRole("presentation");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add class" }));
    expect(await within(dialog).findByText("Name is required")).toBeInTheDocument();
    expect(createClass).not.toHaveBeenCalled();

    await userEvent.type(within(dialog).getByLabelText("Class name"), "9th");
    await userEvent.type(within(dialog).getByLabelText("Code"), "9");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add class" }));

    await waitFor(() =>
      expect(createClass).toHaveBeenCalledWith({
        classCode: "9",
        className: "9th",
        nextClassId: null,
        openForEnrolment: true,
      })
    );
  });

  it("edit: next-class options exclude the class itself; server errors show inline", async () => {
    vi.mocked(updateClass).mockRejectedValue({
      code: "VALIDATION_ERROR",
      message: "Setting 5th as the next class of 7th would create a cycle.",
    });
    render(<ClassCatalogPage />);
    const row7 = await screen.findByTestId("class-row-7");

    await userEvent.click(within(row7).getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("presentation");
    await userEvent.click(within(dialog).getByLabelText("Next class"));
    const options = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(options).toContain("5th");
    expect(options).not.toContain("7th");

    await userEvent.click(screen.getByRole("option", { name: "5th" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await within(dialog).findByText(/would create a cycle/)).toBeInTheDocument();
  });

  it("deactivate from the drawer", async () => {
    vi.mocked(updateClass).mockResolvedValue({ ...CATALOG[3], isActive: false });
    render(<ClassCatalogPage />);
    const row8 = await screen.findByTestId("class-row-8");

    await userEvent.click(within(row8).getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("presentation");
    await userEvent.click(within(dialog).getByRole("button", { name: "Deactivate" }));

    await waitFor(() => expect(updateClass).toHaveBeenCalledWith(4, { isActive: false }));
  });

  it("shows retry when loading fails", async () => {
    vi.mocked(fetchAdminClasses).mockRejectedValueOnce({ code: "SERVER_ERROR" });
    render(<ClassCatalogPage />);

    expect(await screen.findByText("Could not load classes.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("class-row-5")).toBeInTheDocument();
  });
});
