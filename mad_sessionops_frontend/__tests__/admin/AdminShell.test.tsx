import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AdminShell } from "@/components/admin/AdminShell";

const searchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({ useSearchParams: () => searchParams }));
vi.mock("@/components/admin/DataSyncTab", () => ({ DataSyncTab: () => <div>data sync</div> }));
vi.mock("@/components/admin/RealtimeEventsTab", () => ({
  RealtimeEventsTab: () => <div>realtime events</div>,
}));

import { AdminPage } from "@/components/admin/AdminPage";

describe("AdminShell — one frame for every admin screen", () => {
  it("Setup pages keep the full sidebar and mark the current page", () => {
    render(
      <AdminShell active="classes" title="Classes">
        <div>body</div>
      </AdminShell>
    );

    expect(screen.getByRole("heading", { name: "Classes" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /data sync/i })).toHaveAttribute("href", "/admin");
    expect(screen.getByRole("link", { name: /realtime events/i })).toHaveAttribute(
      "href",
      "/admin?tab=realtime-events"
    );
    expect(screen.getByRole("link", { name: /classes/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /year progression/i })).not.toHaveAttribute(
      "aria-current"
    );
  });

  it("/admin opens the tab named in ?tab=", () => {
    searchParams.set("tab", "realtime-events");
    render(<AdminPage />);
    expect(screen.getByText("realtime events")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Realtime Events" })).toBeInTheDocument();
    searchParams.delete("tab");
  });
});
