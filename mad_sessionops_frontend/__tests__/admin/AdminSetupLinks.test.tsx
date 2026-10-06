import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AdminPage } from "@/components/admin/AdminPage";

// The tabs fetch their own data; not under test here.
vi.mock("@/components/admin/DataSyncTab", () => ({ DataSyncTab: () => null }));
vi.mock("@/components/admin/RealtimeEventsTab", () => ({ RealtimeEventsTab: () => null }));

describe("AdminPage — Setup links (F-M10-1)", () => {
  it("links to the Classes, Academic Years and Year Progression setup pages", () => {
    render(<AdminPage />);

    expect(screen.getByText("Setup")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /classes/i })).toHaveAttribute(
      "href",
      "/admin/classes"
    );
    expect(screen.getByRole("link", { name: /academic years/i })).toHaveAttribute(
      "href",
      "/admin/academic-years"
    );
    expect(screen.getByRole("link", { name: /year progression/i })).toHaveAttribute(
      "href",
      "/admin/progression"
    );
  });
});
