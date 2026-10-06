import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";

const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: mockReplace, push: vi.fn() }) }));
vi.mock("@/lib/redux", () => ({ useAppSelector: vi.fn() }));
vi.mock("@/components/admin/progression/ProgressionPage", () => ({
  ProgressionPage: () => <div>progression page</div>,
}));

import { useAppSelector } from "@/lib/redux";
import AdminProgressionRoute from "@/app/admin/progression/page";

const mockSelector = vi.mocked(useAppSelector);

function as(role: string) {
  const state = { auth: { user: { role, name: "x" }, isInitialized: true } };
  mockSelector.mockImplementation((selector) =>
    selector(state as unknown as Parameters<typeof selector>[0])
  );
}

describe("/admin/progression route guard (F-M10-9)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("redirects non-admins (including CXO) to /schools", async () => {
    as("CXO");
    const { container } = render(<AdminProgressionRoute />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/schools"));
    expect(container.firstChild).toBeNull();
  });

  it("renders the page for admins", () => {
    as("CO Full Time,Project Lead");
    const { getByText } = render(<AdminProgressionRoute />);
    expect(getByText("progression page")).toBeInTheDocument();
  });
});
