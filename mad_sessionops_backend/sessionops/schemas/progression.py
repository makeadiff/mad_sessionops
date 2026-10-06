from datetime import datetime

from ninja import Schema
from pydantic import Field


class SchoolProgressionOut(Schema):
    school_progression_id: int
    run_id: int
    school_id: int
    status: str
    error: str | None
    counts: dict
    warnings: list
    started_at: datetime | None
    finished_at: datetime | None

    @staticmethod
    def resolve_run_id(obj) -> int:
        return int(obj.run_id_id)


# ── F-M10-6 precheck / preview ─────────────────────────────────────────────────


class EligibleSchoolOut(Schema):
    school_id: int
    school_name: str
    city: str | None
    current_year_label: str | None
    target_year_label: str | None  # the year after the school's own
    years_behind: int  # how far current_year trails the active year
    eligible: bool
    reason: str | None
    reason_message: str | None


class EligibleSchoolsOut(Schema):
    active_year_label: str | None
    schools: list[EligibleSchoolOut]


class PrecheckIn(Schema):
    school_ids: list[int] = Field(min_length=1, max_length=100)


class IssueOut(Schema):
    code: str
    message: str


class PrecheckOut(Schema):
    school_id: int
    school_name: str
    current_year_label: str | None
    target_year_label: str | None
    status: str
    blockers: list[IssueOut]
    warnings: list[IssueOut]


class SchoolMarksIn(Schema):
    school_id: int
    graduate_class_ids: list[int] = []
    graduate_child_ids: list[int] = []


class PreviewIn(Schema):
    schools: list[SchoolMarksIn] = Field(min_length=1, max_length=100)


class PreviewOut(PrecheckOut):
    counts: dict


class PreviewChildOut(Schema):
    child_id: int
    first_name: str
    last_name: str
    class_id: int | None
    class_name: str | None
    section_name: str | None


class PreviewChildrenPage(Schema):
    total: int
    page: int
    page_size: int
    results: list[PreviewChildOut]


# ── F-M10-7 runs ───────────────────────────────────────────────────────────────


class StartRunIn(Schema):
    # One school per run (start_run enforces it with a clear message too).
    schools: list[SchoolMarksIn] = Field(min_length=1, max_length=1)


class RunOut(Schema):
    """Built by api.admin_progression_api._run_dict (plain fields, no resolvers)."""

    run_id: int
    status: str
    year_moves: list[dict]  # [{"label": "2025-2026 → 2026-2027", "schools": n}]
    started_by_name: str
    started_at: datetime
    finished_at: datetime | None
    cleanup: dict
    school_counts: dict  # {status: n}


class RunSchoolOut(Schema):
    """Built by api.admin_progression_api._school_dict."""

    school_progression_id: int
    run_id: int
    school_id: int
    school_name: str | None = None
    from_year_label: str
    to_year_label: str | None
    status: str
    error: str | None
    counts: dict
    warnings: list
    graduate_class_ids: list
    graduate_child_ids: list
    started_at: datetime | None
    finished_at: datetime | None
    can_undo: bool = False  # F-M10-8
    undo_block_reason: str | None = None


class RunDetailOut(RunOut):
    schools: list[RunSchoolOut]


class RunSchoolDetailOut(RunSchoolOut):
    row_log: dict  # {"created": {table: n}, "archived": {table: n}}
