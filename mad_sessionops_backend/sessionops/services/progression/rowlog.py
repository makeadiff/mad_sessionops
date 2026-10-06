"""F-M10-7: the per-school row log — every row a progression creates or archives.

Used for the audit trail, run-detail summaries and F-M10-8 undo.
"""

from collections import Counter

from sessionops.models import ProgressionRowLog, SchoolProgression


class RowLog:
    """Collects entries during a school's execution; written once, in bulk."""

    def __init__(self, school_progression: SchoolProgression):
        self._sp = school_progression
        self._rows: list[ProgressionRowLog] = []

    def created(self, table: str, row_id: int, source_row_id: int | None = None, **meta) -> None:
        self._rows.append(
            ProgressionRowLog(
                school_progression_id=self._sp,
                table=table,
                row_id=row_id,
                source_row_id=source_row_id,
                action="created",
                meta=meta,
            )
        )

    def archived(self, table: str, row_ids, **meta) -> None:
        for row_id in row_ids:
            self._rows.append(
                ProgressionRowLog(
                    school_progression_id=self._sp,
                    table=table,
                    row_id=row_id,
                    action="archived",
                    meta=meta,
                )
            )

    def flush(self) -> None:
        ProgressionRowLog.objects.bulk_create(self._rows, batch_size=1000)
        self._rows = []


def summary(school_progression: SchoolProgression) -> dict:
    """{"created": {table: n}, "archived": {table: n}} for the run-detail drawer."""
    out: dict[str, Counter[str]] = {"created": Counter(), "archived": Counter()}
    for table, action in school_progression.row_logs.values_list("table", "action"):
        out[action][table] += 1
    return {k: dict(v) for k, v in out.items()}
