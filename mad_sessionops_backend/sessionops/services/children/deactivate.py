from __future__ import annotations

from datetime import datetime

from django.db import models, transaction
from django.utils import timezone

from sessionops.exceptions import NotFound
from sessionops.models import (
    BatchChild,
    Child,
    ChildClass,
    ChildClassSection,
    ChildProgram,
    ChildRemovalLog,
    ClassSection,
    User,
)
from sessionops.schemas.children import DeactivateIn
from sessionops.services.rbac.scope import get_school_or_403
from sessionops.services.structure.bucket_children import assert_bucket_not_over_volunteered

# Links retired together with the child, in db_table order (used by the year-
# progression row log so undo can restore exactly these rows — F-M10-7/8).
_RETIRED_LINKS: tuple[tuple[str, type[models.Model]], ...] = (
    ("child_class", ChildClass),
    ("child_class_section", ChildClassSection),
    ("batch_child", BatchChild),
    ("child_program", ChildProgram),
)


def retire_child(
    child: Child,
    *,
    reason: str,
    other_details: str | None,
    user: User,
    now: datetime | None = None,
) -> dict:
    """Core of deactivation, with no RBAC or R-bucket check: mark the child inactive,
    soft-retire its active placement/program links, and write the removal log.

    Callers own the transaction and the checks — `deactivate_child` (CO flow) and
    year progression's graduation (F-M10-7), which archives the timetable itself.
    Returns the affected ids: {"child_class": [...], ..., "child_removal_log": id}.
    """
    now = now or timezone.now()
    retired: dict = {}

    Child.objects.filter(child_id=child.pk).update(is_active=False, updated_by_id=user.user_id)
    for table, model in _RETIRED_LINKS:
        qs = model._default_manager.filter(child_id=child.pk, is_active=True, removed=False)
        retired[table] = list(qs.values_list("pk", flat=True))
        qs.update(is_active=False, removed=True, deleted_at=now, updated_by_id=user.user_id)

    log = ChildRemovalLog.objects.create(
        child_id=child,
        co_id=user.user_id,
        school_id=child.school_id,
        removed_reason=reason,
        other_details=other_details,
        removed_datetime=now,
        is_active=True,
        removed=False,
    )
    retired["child_removal_log"] = log.pk
    return retired


def deactivate_child(child_id: int, payload: DeactivateIn, user: User) -> None:
    with transaction.atomic():
        try:
            child = Child.objects.select_for_update().get(
                child_id=child_id, is_active=True, removed=False
            )
        except Child.DoesNotExist:
            raise NotFound(f"Child {child_id} not found.")

        get_school_or_403(user, child.school_id)

        # R-bucket: deactivating a child vacates their bucket the same way
        # remove_child_from_bucket does — must not silently leave a scheduled
        # slot-class over-volunteered. Lock the bucket before checking to
        # avoid a lost-update race against a concurrent deactivation/move.
        current_ccs = ChildClassSection.objects.filter(
            child_id=child_id, is_active=True, removed=False
        ).first()
        if current_ccs is not None:
            bucket = ClassSection.objects.select_for_update().get(
                pk=current_ccs.class_section_id_id
            )
            assert_bucket_not_over_volunteered(bucket, current_ccs.child_class_section_id)

        retire_child(
            child,
            reason=payload.removed_reason,
            other_details=payload.other_details,
            user=user,
        )
