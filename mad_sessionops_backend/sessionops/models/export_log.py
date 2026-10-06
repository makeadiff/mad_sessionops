from django.db import models

EXPORT_TYPES = [
    ("school_children", "School children roster"),
    ("school_volunteers", "School volunteer roster"),
    ("school_timetable", "School timetable"),
    ("schools_summary", "Schools summary"),
    ("all_children", "All children in scope"),
    ("all_volunteers", "All volunteers in scope"),
    ("gap_report", "Ops gap report"),
]


class ExportLog(models.Model):
    """F-M9-1: audit row per successful CSV export.

    Append-only — no soft-delete columns, same exception to R9 as RealtimeSyncLog.
    """

    export_log_id = models.BigAutoField(primary_key=True)
    user_id = models.ForeignKey(
        "sessionops.User",
        on_delete=models.PROTECT,
        db_column="user_id",
        related_name="+",
    )
    export_type = models.CharField(max_length=40, choices=EXPORT_TYPES, db_index=True)
    # loose FK to partner.partner_id; null = cross-school export
    school_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    filters = models.JSONField(default=dict)
    school_count = models.IntegerField(default=1)
    row_count = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "export_log"
        indexes = [models.Index(fields=["user_id", "created_at"])]

    def __str__(self) -> str:
        return f"ExportLog({self.export_type}, user={self.user_id_id}, rows={self.row_count})"
