import { describe, it, expect, vi, afterEach } from "vitest";
import { api } from "@/lib/api/client";
import {
  fetchEligibleSchools,
  fetchPreviewChildren,
  precheckSchools,
  previewSchools,
} from "@/lib/api/services/progression.service";

afterEach(() => vi.restoreAllMocks());

type PrecheckBody = { school_ids: number[] };

describe("progression.service — F-M10-6", () => {
  it("maps eligible schools with each school's own move", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({
      active_year_label: "2026-2027",
      schools: [
        {
          school_id: 1,
          school_name: "Behind",
          city: "Pune",
          current_year_label: "2025-2026",
          target_year_label: "2026-2027",
          years_behind: 1,
          eligible: true,
          reason: null,
          reason_message: null,
        },
      ],
    });

    const res = await fetchEligibleSchools();

    expect(get).toHaveBeenCalledWith("/admin/progression/eligible-schools/");
    expect(res.activeYearLabel).toBe("2026-2027");
    expect(res.schools[0]).toMatchObject({
      schoolId: 1,
      currentYearLabel: "2025-2026",
      targetYearLabel: "2026-2027",
      yearsBehind: 1,
    });
  });

  it("prechecks in chunks of 100 and maps results", async () => {
    const post = vi.spyOn(api, "post").mockImplementation(async (_url, body) =>
      (body as PrecheckBody).school_ids.map((id: number) => ({
        school_id: id,
        school_name: `S${id}`,
        current_year_label: "2025-2026",
        target_year_label: "2026-2027",
        status: "ready",
        blockers: [],
        warnings: [],
      }))
    );
    const ids = Array.from({ length: 150 }, (_, i) => i + 1);

    const results = await precheckSchools(ids);

    expect(post).toHaveBeenCalledTimes(2);
    expect((post.mock.calls[0][1] as PrecheckBody).school_ids).toHaveLength(100);
    expect((post.mock.calls[1][1] as PrecheckBody).school_ids).toHaveLength(50);
    expect(results).toHaveLength(150);
    expect(results[0]).toMatchObject({ schoolId: 1, schoolName: "S1", status: "ready" });
  });

  it("sends graduation marks in snake_case and maps counts", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue([
      {
        school_id: 1,
        school_name: "S1",
        current_year_label: "2025-2026",
        status: "warning",
        blockers: [],
        warnings: [{ code: "NO_NEXT_CLASS", message: "…" }],
        counts: {
          school_classes_copied: 4,
          school_classes_added: [],
          sections_copied: 2,
          children_moving: [{ from: "5th", to: "6th", n: 3 }],
          children_staying: [],
          children_graduating: 5,
          volunteers_carried: 1,
          archive_counts: { slot: 2 },
        },
      },
    ]);

    const [res] = await previewSchools([
      { schoolId: 1, graduateClassIds: [8], graduateChildIds: [42] },
    ]);

    expect(post).toHaveBeenCalledWith("/admin/progression/preview/", {
      schools: [{ school_id: 1, graduate_class_ids: [8], graduate_child_ids: [42] }],
    });
    expect(res.counts).toMatchObject({
      schoolClassesCopied: 4,
      childrenMoving: [{ from: "5th", to: "6th", n: 3 }],
      childrenGraduating: 5,
      archiveCounts: { slot: 2 },
    });
  });

  it("child picker sends only set filters", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({
      total: 0,
      page: 1,
      page_size: 50,
      results: [],
    });

    await fetchPreviewChildren(9, { classId: 8, search: "  ", page: 2 });

    expect(get).toHaveBeenCalledWith("/admin/progression/preview/9/children/", {
      params: { class_id: 8, page: 2 },
    });
  });
});
