"""F-M10-2: exactly one active school_academic_year per school.

Aborts (never auto-fixes) if any school already has more than one active row,
listing them, so the data can be corrected deliberately first.
"""

from django.db import migrations, models
from django.db.models import Count


def check_no_duplicates(apps, schema_editor):
    SchoolAcademicYear = apps.get_model("sessionops", "SchoolAcademicYear")
    dupes = list(
        SchoolAcademicYear.objects.using(schema_editor.connection.alias)
        .filter(is_active=True, removed=False)
        .values("school_id")
        .annotate(c=Count("pk"))
        .filter(c__gt=1)
        .values_list("school_id", flat=True)
    )
    if dupes:
        raise RuntimeError(
            f"Schools with >1 active school_academic_year: {sorted(dupes)}. "
            "Archive the extra rows before applying this migration."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("sessionops", "0033_seed_class_catalog"),
    ]

    operations = [
        migrations.RunPython(check_no_duplicates, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="schoolacademicyear",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True), ("removed", False)),
                fields=("school_id",),
                name="uniq_active_say_per_school",
            ),
        ),
    ]
