"""F-M10-5: year progression audit records.

Append/update-only — no soft-delete columns (same R9 exception as ExportLog /
RealtimeSyncLog): runs and their logs are history, never edited away.
"""

from django.db import models

RUN_STATUSES = [
    ("in_progress", "In progress"),
    ("completed", "Completed"),
    ("completed_with_failures", "Completed with failures"),
]

SCHOOL_STATUSES = [
    ("queued", "Queued"),
    ("running", "Running"),
    ("completed", "Completed"),
    ("failed", "Failed"),
    ("undone", "Undone"),
    ("released", "Released"),
]

# A school in one of these is frozen: no user writes, hidden from COs/CHOs.
FROZEN_STATUSES = ("queued", "running", "failed")

ROW_ACTIONS = [("created", "Created"), ("archived", "Archived")]


class ProgressionRun(models.Model):
    run_id = models.BigAutoField(primary_key=True)
    # Legacy (runs before 2026-10-05 had one from/to year). Each school now moves
    # from its own year: see SchoolProgression.to_academic_year_id. Left null on
    # new runs.
    from_academic_year_id = models.ForeignKey(
        "AcademicYear",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="from_academic_year_id",
        related_name="+",
    )
    to_academic_year_id = models.ForeignKey(
        "AcademicYear",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="to_academic_year_id",
        related_name="+",
    )
    started_by = models.ForeignKey("sessionops.User", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=30, choices=RUN_STATUSES, default="in_progress")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    # e.g. {"archived_non_converted_say_ids": [...]}
    cleanup = models.JSONField(default=dict)

    class Meta:
        db_table = "progression_run"
        ordering = ["-run_id"]


class SchoolProgression(models.Model):
    school_progression_id = models.BigAutoField(primary_key=True)
    run_id = models.ForeignKey(
        ProgressionRun,
        on_delete=models.PROTECT,
        db_column="run_id",
        related_name="schools",
    )
    school_id = models.BigIntegerField(db_index=True)
    from_school_academic_year_id = models.ForeignKey(
        "SchoolAcademicYear",
        on_delete=models.PROTECT,
        db_column="from_school_academic_year_id",
        related_name="+",
    )
    # The year this school moves into (the year after its own), fixed at Start.
    to_academic_year_id = models.ForeignKey(
        "AcademicYear",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="to_academic_year_id",
        related_name="+",
    )
    to_school_academic_year_id = models.ForeignKey(
        "SchoolAcademicYear",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="to_school_academic_year_id",
        related_name="+",
    )
    status = models.CharField(max_length=20, choices=SCHOOL_STATUSES, default="queued")
    graduate_class_ids = models.JSONField(default=list)
    graduate_child_ids = models.JSONField(default=list)
    counts = models.JSONField(default=dict)
    warnings = models.JSONField(default=list)
    error = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    undone_at = models.DateTimeField(null=True, blank=True)
    undone_by = models.ForeignKey(
        "sessionops.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "school_progression"
        indexes = [models.Index(fields=["school_id", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["school_id"],
                condition=models.Q(status__in=FROZEN_STATUSES),
                name="uniq_unfinished_progression_per_school",
            ),
        ]


class ProgressionRowLog(models.Model):
    row_log_id = models.BigAutoField(primary_key=True)
    school_progression_id = models.ForeignKey(
        SchoolProgression,
        on_delete=models.PROTECT,
        db_column="school_progression_id",
        related_name="row_logs",
    )
    table = models.CharField(max_length=50)  # Django db_table name
    row_id = models.BigIntegerField()
    source_row_id = models.BigIntegerField(null=True, blank=True)  # old id, for created rows
    action = models.CharField(max_length=10, choices=ROW_ACTIONS)
    # e.g. {"restore_removed": true} for links retired by graduation (F-M10-8 undo)
    meta = models.JSONField(default=dict)

    class Meta:
        db_table = "progression_row_log"
        indexes = [models.Index(fields=["school_progression_id", "table"])]
