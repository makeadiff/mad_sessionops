import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import apiClient, { api, download, filenameFromDisposition } from "@/lib/api/client";
import {
  exportAllChildren,
  exportAllVolunteers,
  exportGapReport,
  exportParams,
  exportSchoolChildren,
  exportSchoolTimetable,
  exportSchoolsSummary,
  exportSchoolVolunteers,
} from "@/lib/api/services/exports.service";

describe("filenameFromDisposition", () => {
  it("extracts quoted and unquoted filenames", () => {
    expect(filenameFromDisposition('attachment; filename="children_1_2026-09-27.csv"')).toBe(
      "children_1_2026-09-27.csv"
    );
    expect(filenameFromDisposition("attachment; filename=x.csv")).toBe("x.csv");
  });

  it("returns undefined when absent", () => {
    expect(filenameFromDisposition(undefined)).toBeUndefined();
    expect(filenameFromDisposition("attachment")).toBeUndefined();
  });
});

describe("download", () => {
  let clicked: string[];

  beforeEach(() => {
    clicked = [];
    window.URL.createObjectURL = vi.fn(() => "blob:mock");
    window.URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement
    ) {
      clicked.push(this.download);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses the Content-Disposition filename and passes params", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      data: new Blob(["a,b\r\n"]),
      headers: {
        "content-disposition": 'attachment; filename="children_7_2026-09-27.csv"',
        "content-type": "text/csv; charset=utf-8",
      },
    });

    await download("/schools/7/exports/children.csv", "children.csv", { status: "all" });

    expect(get).toHaveBeenCalledWith(
      "/schools/7/exports/children.csv",
      expect.objectContaining({ params: { status: "all" }, responseType: "blob" })
    );
    expect(clicked).toEqual(["children_7_2026-09-27.csv"]);
  });

  it("falls back to the given filename when the header is missing", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: new Blob(["x"]), headers: {} });

    await download("/exports/schools.csv", "schools.csv");

    expect(clicked).toEqual(["schools.csv"]);
  });

  it("turns a JSON error blob into the backend message", async () => {
    const body = JSON.stringify({
      error: { code: "not_found", message: "No active academic year is configured." },
    });
    vi.spyOn(apiClient, "get").mockRejectedValue({
      message: "The requested resource was not found.",
      code: "NOT_FOUND",
      status: 404,
      data: new Blob([body], { type: "application/json" }),
    });

    await expect(download("/exports/schools.csv", "schools.csv")).rejects.toMatchObject({
      code: "NOT_FOUND",
      message: "No active academic year is configured.",
    });
    expect(clicked).toEqual([]);
  });

  it("keeps the generic message for 403", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue({
      message: "You do not have permission to perform this action.",
      code: "FORBIDDEN",
      status: 403,
      data: new Blob([JSON.stringify({ error: { message: "Permission denied." } })]),
    });

    await expect(download("/schools/1/exports/children.csv", "c.csv")).rejects.toMatchObject({
      message: "You do not have permission to perform this action.",
    });
  });
});

describe("exportParams", () => {
  it("drops empty values and keeps strings exactly as given", () => {
    expect(exportParams({ search: "pune ", status: "", page: 0, x: null, y: undefined })).toEqual({
      search: "pune ",
      page: 0,
    });
  });

  it("sends true as 'true' and drops false", () => {
    expect(exportParams({ unassigned: true, other: false })).toEqual({ unassigned: "true" });
  });
});

describe("exportSchoolChildren", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("builds the children export URL and params", async () => {
    const dl = vi.spyOn(api, "download").mockResolvedValue(undefined);

    await exportSchoolChildren(580, {
      status: "active",
      search: "",
      classId: 3,
      sectionId: null,
      unassigned: true,
    });

    expect(dl).toHaveBeenCalledWith("/schools/580/exports/children.csv", "children_580.csv", {
      status: "active",
      class_id: 3,
      unassigned: "true",
    });
  });
});

describe("exportSchoolVolunteers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("builds the volunteers export URL", async () => {
    const dl = vi.spyOn(api, "download").mockResolvedValue(undefined);

    await exportSchoolVolunteers(580);

    expect(dl).toHaveBeenCalledWith("/schools/580/exports/volunteers.csv", "volunteers_580.csv");
  });
});

describe("exportSchoolTimetable", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("builds the timetable export URL", async () => {
    const dl = vi.spyOn(api, "download").mockResolvedValue(undefined);

    await exportSchoolTimetable(580);

    expect(dl).toHaveBeenCalledWith("/schools/580/exports/timetable.csv", "timetable_580.csv");
  });
});

describe("exportSchoolsSummary", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends the search only when set", async () => {
    const dl = vi.spyOn(api, "download").mockResolvedValue(undefined);

    await exportSchoolsSummary("pune");
    await exportSchoolsSummary("");

    expect(dl).toHaveBeenNthCalledWith(1, "/exports/schools.csv", "schools_all.csv", {
      search: "pune",
    });
    expect(dl).toHaveBeenNthCalledWith(2, "/exports/schools.csv", "schools_all.csv", {});
  });
});

describe("exportAllChildren", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("builds the all-children export URL with status=all", async () => {
    const dl = vi.spyOn(api, "download").mockResolvedValue(undefined);

    await exportAllChildren("pune");

    expect(dl).toHaveBeenCalledWith("/exports/children.csv", "children_all.csv", {
      search: "pune",
      status: "all",
    });
  });
});

describe("exportAllVolunteers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("builds the all-volunteers export URL", async () => {
    const dl = vi.spyOn(api, "download").mockResolvedValue(undefined);

    await exportAllVolunteers("pune");

    expect(dl).toHaveBeenCalledWith("/exports/volunteers.csv", "volunteers_all.csv", {
      search: "pune",
    });
  });
});

describe("exportGapReport", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("builds the gap report URL", async () => {
    const dl = vi.spyOn(api, "download").mockResolvedValue(undefined);

    await exportGapReport("pune");

    expect(dl).toHaveBeenCalledWith("/exports/gaps.csv", "gaps_all.csv", { search: "pune" });
  });
});
