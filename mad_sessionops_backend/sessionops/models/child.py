from django.db import models

REMOVED_REASONS = [
    ("inactive", "Inactive"),
    ("duplicate_entry", "Duplicate entry"),
    ("wrong_school_class", "Added to wrong school/class by mistake"),
    ("transferred", "Transferred to another school"),
    ("dropped_out", "Dropped out of school"),
    ("family_declined", "Family does not want the child enrolled"),
    ("child_declined", "Child no longer interested in participating"),
    ("other", "Other"),
    # M10: set only by year progression (preview graduation marks) — not offered in
    # the CO Deactivate dialog (DeactivateIn doesn't accept it).
    ("graduated", "Graduated"),
]


class Child(models.Model):
    child_id = models.BigAutoField(primary_key=True)
    school_id = models.BigIntegerField(db_index=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(
        max_length=20,
        choices=[("male", "Male"), ("female", "Female"), ("other", "Other")],
    )
    date_of_birth = models.DateField(null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    mother_tongue = models.CharField(max_length=50, null=True, blank=True)
    date_of_enrollment = models.DateField(null=True, blank=True)
    mad_joining_date = models.DateField(null=True, blank=True)
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
        db_table = "child"
        indexes = [models.Index(fields=["school_id", "is_active", "removed"])]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"


class ChildClass(models.Model):
    child_class_id = models.BigAutoField(primary_key=True)
    child_id = models.ForeignKey(Child, on_delete=models.PROTECT, db_column="child_id")
    school_class_id = models.ForeignKey(
        "sessionops.SchoolClass", on_delete=models.PROTECT, db_column="school_class_id"
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
        db_table = "child_class"
        indexes = [
            models.Index(fields=["child_id", "is_active"]),
            models.Index(fields=["school_class_id", "is_active"]),
        ]


class ChildClassSection(models.Model):
    child_class_section_id = models.BigAutoField(primary_key=True)
    child_id = models.ForeignKey(Child, on_delete=models.PROTECT, db_column="child_id")
    class_section_id = models.ForeignKey(
        "sessionops.ClassSection", on_delete=models.PROTECT, db_column="class_section_id"
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
        db_table = "child_class_section"
        indexes = [
            models.Index(fields=["child_id", "is_active"]),
            models.Index(fields=["class_section_id", "is_active"]),
        ]


class BatchChild(models.Model):
    batch_child_id = models.BigAutoField(primary_key=True)
    school_academic_year_id = models.ForeignKey(
        "sessionops.SchoolAcademicYear",
        on_delete=models.PROTECT,
        db_column="school_academic_year_id",
    )
    child_id = models.ForeignKey(Child, on_delete=models.PROTECT, db_column="child_id")
    school_id = models.BigIntegerField(db_index=True)
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
        db_table = "batch_child"


class ChildProgram(models.Model):
    child_program_id = models.BigAutoField(primary_key=True)
    program_id = models.ForeignKey(
        "sessionops.Program", on_delete=models.PROTECT, db_column="program_id"
    )
    child_id = models.ForeignKey(Child, on_delete=models.PROTECT, db_column="child_id")
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
        db_table = "child_program"


class ChildRemovalLog(models.Model):
    child_removal_log_id = models.BigAutoField(primary_key=True)
    child_id = models.ForeignKey(Child, on_delete=models.PROTECT, db_column="child_id")
    co_id = models.BigIntegerField()  # loose FK to user.user_id
    school_id = models.BigIntegerField(db_index=True)
    removed_reason = models.CharField(max_length=20, choices=REMOVED_REASONS)
    other_details = models.TextField(null=True, blank=True)
    removed_datetime = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    removed = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "child_removal_log"
        indexes = [models.Index(fields=["child_id", "is_active"])]
