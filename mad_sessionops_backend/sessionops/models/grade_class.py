from django.db import models


class Class(models.Model):
    class_id = models.BigAutoField(primary_key=True)
    class_name = models.CharField(max_length=20)  # "5th", "6th"
    class_code = models.CharField(max_length=4, unique=True)  # "5", "6"
    program_id = models.ForeignKey(
        "sessionops.Program", on_delete=models.PROTECT, db_column="program_id"
    )
    # F-M10-1: admin-managed catalog. `sequence` is a derived sort key, rewritten
    # from the next-class chain on every catalog write (services/catalog/order.py)
    # — never admin input; `next_class_id` is where year progression moves
    # children (null = they stay in this class); `open_for_enrolment` replaces
    # the old hard-coded BLOCKED_NEW_CLASS_CODES.
    sequence = models.IntegerField(default=0, db_index=True)
    next_class_id = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="next_class_id",
        related_name="previous_classes",
    )
    open_for_enrolment = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    removed = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "sessionops.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    updated_by = models.ForeignKey(
        "sessionops.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "class"
        ordering = ["sequence", "class_code"]

    def __str__(self) -> str:
        return self.class_name


class SchoolClass(models.Model):
    school_class_id = models.BigAutoField(primary_key=True)
    school_id = models.BigIntegerField(db_index=True)
    school_academic_year_id = models.ForeignKey(
        "sessionops.SchoolAcademicYear",
        on_delete=models.PROTECT,
        db_column="school_academic_year_id",
    )
    # db_column prevents Django from creating column "class_id_id"
    class_id = models.ForeignKey(Class, on_delete=models.PROTECT, db_column="class_id")
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
        db_table = "school_class"
        constraints = [
            models.UniqueConstraint(
                fields=["school_id", "school_academic_year_id", "class_id"],
                condition=models.Q(removed=False),
                name="uniq_school_class_per_year",
            ),
        ]

    def __str__(self) -> str:
        return f"School {self.school_id} — {self.class_id}"
