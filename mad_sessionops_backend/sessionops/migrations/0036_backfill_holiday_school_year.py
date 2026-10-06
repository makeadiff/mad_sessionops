"""F-M10-4: link existing holidays to their school's single active school-year.

Holidays of schools with no active school-year stay null (a documented legacy
fallback: still listed). The reverse is a no-op; 0035's RemoveField drops the column.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    db = schema_editor.connection.alias
    SchoolHoliday = apps.get_model("sessionops", "SchoolHoliday")
    SchoolAcademicYear = apps.get_model("sessionops", "SchoolAcademicYear")
    say_by_school = dict(
        SchoolAcademicYear.objects.using(db)
        .filter(is_active=True, removed=False)
        .values_list("school_id", "school_academic_year_id")
    )
    linked = unlinked = 0
    for holiday in SchoolHoliday.objects.using(db).filter(school_academic_year_id__isnull=True):
        say_id = say_by_school.get(holiday.school_id)
        if say_id is None:
            unlinked += 1
            continue
        holiday.school_academic_year_id_id = say_id
        holiday.save(using=db, update_fields=["school_academic_year_id"])
        linked += 1
    print(f"\n  Holidays linked to a school-year: {linked}; left null (no school-year): {unlinked}")


class Migration(migrations.Migration):
    dependencies = [
        ("sessionops", "0035_holiday_school_year"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
