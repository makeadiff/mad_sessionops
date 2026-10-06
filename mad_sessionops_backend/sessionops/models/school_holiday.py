from django.db import models

HOLIDAY_REASONS = [
    ("mad_event", "MAD event (eg: YEC, etc)"),
    ("holidays", "Holidays"),
    ("cancelled_from_school_end", "Cancelled from school's end"),
]


class SchoolHoliday(models.Model):
    """
    Per-school holiday entry within the active academic session window.

    Date ranges (single-day = start_date == end_date). Holidays must fall
    inside the session window and cannot overlap other active holidays at
    the same school.

    Date edits use soft-delete + create-new to preserve audit history.
    Metadata edits (reason, description, remarks) update in place.
    """

    school_holiday_id = models.BigAutoField(primary_key=True)
    school_id = models.BigIntegerField(db_index=True)
    # F-M10-4: the school-year this holiday belongs to. Year progression doesn't
    # archive holidays; reads filter to the school's active school-year, so old
    # ones drop out of view. Null = legacy row (kept visible as a fallback).
    school_academic_year_id = models.ForeignKey(
        "SchoolAcademicYear",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="school_academic_year_id",
        related_name="+",
    )
    holiday_reason = models.CharField(max_length=50, choices=HOLIDAY_REASONS)
    start_date = models.DateField()
    end_date = models.DateField()
    holiday_description = models.TextField(null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    removed = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey("sessionops.User", on_delete=models.PROTECT, related_name="+")
    updated_by = models.ForeignKey(
        "sessionops.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "school_holiday"
        indexes = [
            models.Index(fields=["school_id", "is_active", "removed"]),
            models.Index(fields=["school_id", "start_date", "end_date"]),
        ]

    def __str__(self) -> str:
        return f"Holiday(school={self.school_id}, {self.start_date}–{self.end_date}, {self.holiday_reason})"

    def get_holiday_reason_display_value(self) -> str:
        return dict(HOLIDAY_REASONS).get(self.holiday_reason, self.holiday_reason)
