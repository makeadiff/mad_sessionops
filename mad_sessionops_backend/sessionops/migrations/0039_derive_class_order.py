"""Derive Class.sequence from the next-class chain once (it is no longer admin input).

From here on services/catalog/order.py::recompute_sequences keeps it in step on
every catalog write. Reverse is a no-op: the old values were only a sort key.
"""

from django.db import migrations

from sessionops.services.catalog.order import compute_order


def derive(apps, schema_editor):
    Class = apps.get_model("sessionops", "Class")
    db = schema_editor.connection.alias  # same connection as the migration (no lock waits)
    classes = list(Class.objects.using(db).filter(removed=False))
    changed = []
    for position, cls in enumerate(compute_order(classes), start=1):
        if cls.sequence != position:
            cls.sequence = position
            changed.append(cls)
    Class.objects.using(db).bulk_update(changed, ["sequence"])


class Migration(migrations.Migration):
    dependencies = [("sessionops", "0038_removal_reason_graduated")]

    operations = [migrations.RunPython(derive, migrations.RunPython.noop)]
