import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExportButton } from "@/components/ui/ExportButton";
import { showError } from "@/lib/toast/toast";

vi.mock("@/lib/toast/toast", () => ({
  showError: vi.fn(),
}));

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((r) => (resolve = r));
  return { promise, resolve };
}

describe("ExportButton", () => {
  beforeEach(() => {
    vi.mocked(showError).mockClear();
  });

  it("single option: click runs the export, shows busy state and blocks repeat clicks", async () => {
    const pending = deferred();
    const onExport = vi.fn(() => pending.promise);
    render(<ExportButton options={[{ label: "Children", onExport }]} />);

    const button = screen.getByRole("button", { name: /export csv/i });
    await userEvent.click(button);

    expect(onExport).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("progressbar")).toBeInTheDocument();

    pending.resolve();
    await waitFor(() => expect(button).not.toBeDisabled());
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("multiple options: opens a menu and runs the chosen export", async () => {
    const first = vi.fn().mockResolvedValue(undefined);
    const second = vi.fn().mockResolvedValue(undefined);
    render(
      <ExportButton
        label="Export"
        options={[
          { label: "Schools summary", onExport: first },
          { label: "Gap report", onExport: second },
        ]}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /export/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Gap report" }));

    await waitFor(() => expect(second).toHaveBeenCalledTimes(1));
    expect(first).not.toHaveBeenCalled();
  });

  it("shows the backend message in an error toast when the export fails", async () => {
    const onExport = vi
      .fn()
      .mockRejectedValue({ code: "NOT_FOUND", message: "No active academic year is configured." });
    render(<ExportButton options={[{ label: "Children", onExport }]} />);

    await userEvent.click(screen.getByRole("button", { name: /export csv/i }));

    await waitFor(() =>
      expect(showError).toHaveBeenCalledWith("No active academic year is configured.")
    );
    expect(screen.getByRole("button", { name: /export csv/i })).not.toBeDisabled();
  });

  it("does not toast on session expiry", async () => {
    const onExport = vi.fn().mockRejectedValue({ code: "SESSION_EXPIRED", message: "x" });
    render(<ExportButton options={[{ label: "Children", onExport }]} />);

    await userEvent.click(screen.getByRole("button", { name: /export csv/i }));

    await waitFor(() => expect(onExport).toHaveBeenCalled());
    expect(showError).not.toHaveBeenCalled();
  });

  it("is disabled when there are no options", () => {
    render(<ExportButton options={[]} />);
    expect(screen.getByRole("button", { name: /export csv/i })).toBeDisabled();
  });
});
