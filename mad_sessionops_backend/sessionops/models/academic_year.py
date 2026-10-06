from django.db import models


class AcademicYear(models.Model):
    academic_year_id = models.BigAutoField(primary_key=True)
    label = models.CharField(max_length=20, unique=True)  # "2026-2027"
    is_active = models.BooleanField(default=False)
    removed = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey("sessionops.User", on_delete=models.PROTECT, related_name="+")
    updated_by = models.ForeignKey(
        "sessionops.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "academic_year"
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="uniq_active_academic_year",
            ),
        ]

    def __str__(self) -> str:
        return self.label


class SchoolAcademicYear(models.Model):
    school_academic_year_id = models.BigAutoField(primary_key=True)
    school_id = models.BigIntegerField(db_index=True)
    academic_year_id = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, db_column="academic_year_id"
    )
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
        db_table = "school_academic_year"
        constraints = [
            models.UniqueConstraint(
                fields=["school_id", "academic_year_id"],
                condition=models.Q(removed=False),
                name="uniq_school_academic_year",
            ),
            # F-M10-2: a school has exactly one active school-year; every year-scoped
            # read and write relies on it.
            models.UniqueConstraint(
                fields=["school_id"],
                condition=models.Q(is_active=True, removed=False),
                name="uniq_active_say_per_school",
            ),
        ]

    def __str__(self) -> str:
        return f"School {self.school_id} — {self.academic_year_id}"
