import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SchoolToolbar } from "@/components/schools/SchoolToolbar";

describe("SchoolToolbar — F-M9-5 export", () => {
  const base = {
    search: "",
    onSearchChange: vi.fn(),
    sort: "updated_desc" as const,
    onSortChange: vi.fn(),
  };

  it("test_export_hidden_without_options", () => {
    render(<SchoolToolbar {...base} />);
    expect(screen.queryByRole("button", { name: /^export$/i })).not.toBeInTheDocument();
  });

  it("test_export_shown_with_options", () => {
    render(
      <SchoolToolbar
        {...base}
        exportOptions={[
          { label: "Schools summary", onExport: vi.fn().mockResolvedValue(undefined) },
        ]}
      />
    );
    expect(screen.getByRole("button", { name: /^export$/i })).toBeInTheDocument();
  });
});
