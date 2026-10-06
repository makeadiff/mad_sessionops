"""F-M10-5: the school freeze during year progression.

A school whose SchoolProgression is queued / running / failed is frozen:
- every user write to /api/schools/{id}/… returns 409 school_progressing
  (middleware/progression_freeze.py — one central guard for every write router);
- it is hidden from COs/CHOs (rbac/scope.py) and read-only for admins.
System syncs (realtime / partner sync) use other URL prefixes and are not blocked;
F-M10-7 execution locks the school-year row so they wait instead.
"""

from django.db import transaction
from django.utils import timezone

from sessionops.exceptions import ConflictError
from sessionops.models import FROZEN_STATUSES, SchoolProgression, User


def frozen_school_ids() -> set[int]:
    return set(
        SchoolProgression.objects.filter(status__in=FROZEN_STATUSES).values_list(
            "school_id", flat=True
        )
    )


def is_school_frozen(school_id: int) -> bool:
    return SchoolProgression.objects.filter(
        school_id=school_id, status__in=FROZEN_STATUSES
    ).exists()


def recompute_run_status(run) -> None:
    """completed when nothing is left queued/running/failed; completed_with_failures
    when some school failed and nothing is queued/running; otherwise in_progress."""
    statuses = set(run.schools.values_list("status", flat=True))
    if statuses & {"queued", "running"}:
        status = "in_progress"
    elif "failed" in statuses:
        status = "completed_with_failures"
    else:
        status = "completed"
    if status != run.status:
        run.status = status
        run.finished_at = None if status == "in_progress" else timezone.now()
        run.save(update_fields=["status", "finished_at"])


@transaction.atomic
def release_school(school_progression: SchoolProgression, user: User) -> SchoolProgression:
    """Unfreeze a FAILED school on its old year without retrying (status → released)."""
    sp = SchoolProgression.objects.select_for_update().get(pk=school_progression.pk)
    if sp.status != "failed":
        raise ConflictError(
            f"Only a failed school can be released (this one is {sp.status}).",
            error_code="release_not_allowed",
        )
    sp.status = "released"
    sp.finished_at = timezone.now()
    sp.save(update_fields=["status", "finished_at", "updated_at"])
    recompute_run_status(sp.run_id)
    return sp
