"""F-M10-1: seed the admin-managed catalog fields from the current catalog.

- sequence = int(class_code) when numeric, else 1000 (sorts last)
- next_class: 5 -> 6 -> 7 -> 8 (8 has none: children stay)
- open_for_enrolment = False for "8" (was the hard-coded BLOCKED_NEW_CLASS_CODES)
"""

from django.db import migrations

NEXT_BY_CODE = {"5": "6", "6": "7", "7": "8"}
CLOSED_CODES = {"8"}


def seed(apps, schema_editor):
    Class = apps.get_model("sessionops", "Class")
    db = schema_editor.connection.alias
    by_code = {c.class_code: c for c in Class.objects.using(db).all()}
    for code, cls in by_code.items():
        cls.sequence = int(code) if code.isdigit() else 1000
        cls.open_for_enrolment = code not in CLOSED_CODES
        nxt = by_code.get(NEXT_BY_CODE.get(code, ""))
        cls.next_class_id = nxt
        cls.save(using=db, update_fields=["sequence", "open_for_enrolment", "next_class_id"])


def unseed(apps, schema_editor):
    Class = apps.get_model("sessionops", "Class")
    db = schema_editor.connection.alias
    Class.objects.using(db).update(sequence=0, open_for_enrolment=True, next_class_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ("sessionops", "0032_class_catalog_fields"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
