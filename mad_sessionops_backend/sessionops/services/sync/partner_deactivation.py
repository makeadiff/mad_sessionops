"""
F-M4-9: Partner deactivation cascade.

Triggered from bulk_upsert_partners (services/sync/upsert.py) when a Hasura
partner row reports crm_partner_removed=False and converted=False while the
partner was previously active in Session-Ops. Interpreted as "reverted to a
non-converted CRM stage without being formally removed" — treated the same
as an offboarded school: every operational record under the school is
cascade-deactivated, and the Partner row itself is deactivated.

This is independent of and takes priority over F-M1-2's existing
crm_partner_removed-only flag flip (Partner.is_active = not crm_partner_removed).
"""

from __future__ import annotations

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from sessionops.models import (
    BatchChild,
    Child,
    ChildClass,
    ChildClassSection,
    ChildProgram,
    ChildRemovalLog,
    ChildSubject,
    ClassSection,
    ClassSectionSubject,
    Partner,
    SchoolAcademicYear,
    SchoolClass,
    SchoolHoliday,
    SchoolSessionDetails,
    SchoolVolunteer,
    Slot,
    SlotClassSection,
    SlotClassSectionVolunteer,
)

# System actor for sync-triggered ChildRemovalLog rows (mandatory field, no
# human operator to attribute the removal to). Matches the M7 migration
# precedent of using a real existing user_id rather than an invented bot user.
SYSTEM_SYNC_CO_ID = 485003

CHILD_REMOVAL_REASON = "other"
CHILD_REMOVAL_OTHER_DETAILS = "School dropped from CRM"


def cascade_deactivate_school(school_id: int, now: datetime | None = None) -> dict[str, int]:
    """
    Cascade-deactivate every active operational record under school_id.

    Idempotent: every query filters is_active=True (and removed=False where
    that field exists), so calling this again against an already-cascaded
    school finds nothing to touch and returns all-zero counts.

    Runs inside its own transaction.atomic() with the Partner row locked for
    the duration, so a concurrent write against the same school can't
    interleave with the cascade.
    """
    now = now or timezone.now()
    counts: dict[str, int] = {}

    with transaction.atomic():
        Partner.all_objects.select_for_update().filter(partner_id=school_id).first()

        counts["slot_class_section_volunteer"] = SlotClassSectionVolunteer.objects.filter(
            slot_class_section_id__slot_id__school_id=school_id,
            is_active=True,
            removed=False,
        ).update(is_active=False, removed=True, deleted_at=now)

        counts["slot_class_section"] = SlotClassSection.objects.filter(
            slot_id__school_id=school_id, is_active=True, removed=False
        ).update(is_active=False, removed=True, deleted_at=now)

        counts["slot"] = Slot.objects.filter(
            school_id=school_id, is_active=True, removed=False
        ).update(is_active=False, removed=True, deleted_at=now)

        counts["class_section_subject"] = ClassSectionSubject.objects.filter(
            class_section_id__school_id=school_id, is_active=True, removed=False
        ).update(is_active=False, removed=True, deleted_at=now)

        counts["school_volunteer"] = SchoolVolunteer.objects.filter(
            school_id=school_id, is_active=True, removed=False
        ).update(is_active=False, removed=True, deleted_at=now)

        counts["child_class_section"] = ChildClassSection.objects.filter(
            child_id__school_id=school_id, is_active=True, removed=False
        ).update(is_active=False, removed=True, deleted_at=now)

        # Child-level links that would otherwise stay active under removed
        # children (enrolment-in-year, program, subject history).
        counts["batch_child"] = BatchChild.objects.filter(
            school_id=school_id, is_active=True, removed=False
        ).update(is_active=False, removed=True, deleted_at=now)

        counts["child_program"] = ChildProgram.objects.filter(
            child_id__school_id=school_id, is_active=True, removed=False
        ).update(is_active=False, removed=True, deleted_at=now)

        counts["child_subject"] = ChildSubject.objects.filter(
            child_id__school_id=school_id, is_active=True, removed=False
        ).update(is_active=False, removed=True, deleted_at=now)

        active_child_ids = list(
            Child.objects.filter(school_id=school_id, is_active=True, removed=False).values_list(
                "child_id", flat=True
            )
        )
        ChildRemovalLog.objects.bulk_create(
            ChildRemovalLog(
                child_id_id=child_id,
                co_id=SYSTEM_SYNC_CO_ID,
                school_id=school_id,
                removed_reason=CHILD_REMOVAL_REASON,
                other_details=CHILD_REMOVAL_OTHER_DETAILS,
                removed_datetime=now,
            )
            for child_id in active_child_ids
        )
        counts["child_removal_log"] = len(active_child_ids)

        counts["child"] = Child.objects.filter(child_id__in=active_child_ids).update(
            is_active=False, removed=True, deleted_at=now
        )

        counts["child_class"] = ChildClass.objects.filter(
            child_id__school_id=school_id, is_active=True, removed=False
        ).update(is_active=False, removed=True, deleted_at=now)

        counts["class_section"] = ClassSection.objects.filter(
            school_id=school_id, is_active=True, removed=False
        ).update(is_active=False, removed=True, deleted_at=now)

        counts["school_class"] = SchoolClass.objects.filter(
            school_id=school_id, is_active=True, removed=False
        ).update(is_active=False, removed=True, deleted_at=now)

        counts["school_academic_year"] = SchoolAcademicYear.objects.filter(
            school_id=school_id, is_active=True, removed=False
        ).update(is_active=False, removed=True, deleted_at=now)

        counts["school_session_details"] = SchoolSessionDetails.objects.filter(
            school_id=school_id, is_active=True, removed=False
        ).update(is_active=False, removed=True, deleted_at=now)

        counts["school_holiday"] = SchoolHoliday.objects.filter(
            school_id=school_id, is_active=True, removed=False
        ).update(is_active=False, removed=True, deleted_at=now)

        counts["partner"] = Partner.all_objects.filter(partner_id=school_id, is_active=True).update(
            is_active=False, deleted_at=now
        )

    return counts
