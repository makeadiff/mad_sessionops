"""F-M10-8: undo one school's completed progression, driven by its row log.

Allowed only until anyone writes new-year data for that school:
- no year-bound row on the new school-year exists outside the progression's own
  created rows (classes, sections, slots, school volunteers, batch rows, sessions,
  holidays);
- no child placement points at the new classes/sections outside the log;
- no child was enrolled at the school after the progression finished;
- no row the progression created or archived has been edited since.

Undo is one transaction: created rows are soft-deleted FIRST (so the one-active-
school-year and section-slug constraints never clash), then archived rows are
restored — graduates are reactivated and their "graduated" removal log retired.
The global academic year is never flipped back.
"""

from django.db import models, transaction
from django.utils import timezone

from sessionops.exceptions import ConflictError
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
    ProgressionRowLog,
    SchoolAcademicYear,
    SchoolClass,
    SchoolHoliday,
    SchoolProgression,
    SchoolSessionDetails,
    SchoolVolunteer,
    Slot,
    SlotClassSection,
    SlotClassSectionVolunteer,
    User,
)
from sessionops.services.progression.freeze import recompute_run_status

MODELS: dict[str, type[models.Model]] = {
    "school_academic_year": SchoolAcademicYear,
    "school_class": SchoolClass,
    "class_section": ClassSection,
    "child": Child,
    "child_class": ChildClass,
    "child_class_section": ChildClassSection,
    "batch_child": BatchChild,
    "child_program": ChildProgram,
    "child_removal_log": ChildRemovalLog,
    "school_volunteer": SchoolVolunteer,
    "slot": Slot,
    "slot_class_section": SlotClassSection,
    "slot_class_section_volunteer": SlotClassSectionVolunteer,
    "class_section_subject": ClassSectionSubject,
    "child_subject": ChildSubject,
    "school_session_details": SchoolSessionDetails,
}

# Year-bound tables whose rows on the NEW school-year must all be the run's own.
_YEAR_BOUND: tuple[tuple[str, type[models.Model], str], ...] = (
    ("school_class", SchoolClass, "school_academic_year_id"),
    ("class_section", ClassSection, "school_academic_year_id"),
    ("slot", Slot, "school_academic_year_id"),
    ("school_volunteer", SchoolVolunteer, "school_academic_year_id"),
    ("batch_child", BatchChild, "school_academic_year_id"),
    ("school_session_details", SchoolSessionDetails, "school_academic_year"),
    ("school_holiday", SchoolHoliday, "school_academic_year_id"),
)

_LABELS = {
    "school_class": "a class",
    "class_section": "a bucket/section",
    "slot": "a slot",
    "school_volunteer": "a school volunteer",
    "batch_child": "a child's year record",
    "school_session_details": "term dates",
    "school_holiday": "a holiday",
}


def _logged(sp: SchoolProgression, action: str) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    for table, row_id in ProgressionRowLog.objects.filter(
        school_progression_id=sp, action=action
    ).values_list("table", "row_id"):
        out.setdefault(table, set()).add(row_id)
    return out


def can_undo(sp: SchoolProgression) -> tuple[bool, str | None]:
    if sp.status != "completed":
        return (
            False,
            f"Only a completed school can be undone (this one is {sp.status}).",
        )
    new_say_id = sp.to_school_academic_year_id_id
    if new_say_id is None:
        return False, "This progression has no new academic year to undo."

    created = _logged(sp, "created")
    label = (
        SchoolAcademicYear.objects.filter(pk=new_say_id)
        .values_list("academic_year_id__label", flat=True)
        .first()
    ) or "the new year"

    for table, model, field in _YEAR_BOUND:
        ids = set(model._default_manager.filter(**{field: new_say_id}).values_list("pk", flat=True))
        if ids - created.get(table, set()):
            return (
                False,
                f"{_LABELS[table].capitalize()} was added in {label} after progression.",
            )

    new_classes = created.get("school_class", set())
    extra_cc = ChildClass.objects.filter(school_class_id__in=new_classes).exclude(
        pk__in=created.get("child_class", set())
    )
    if extra_cc.exists():
        return False, f"A child was placed in a {label} class after progression."
    extra_ccs = ChildClassSection.objects.filter(
        class_section_id__in=created.get("class_section", set())
    ).exclude(pk__in=created.get("child_class_section", set()))
    if extra_ccs.exists():
        return False, f"A child was placed in a {label} bucket after progression."

    if Child.objects.filter(school_id=sp.school_id, created_at__gt=sp.finished_at).exists():
        return False, "A child was enrolled at this school after progression."

    for action in ("created", "archived"):
        for table, ids in _logged(sp, action).items():
            logged_model = MODELS.get(table)
            if logged_model is None:
                continue
            if logged_model._default_manager.filter(
                pk__in=ids, updated_at__gt=sp.finished_at
            ).exists():
                return False, "Data changed by this progression has been edited since."
    return True, None


@transaction.atomic
def undo_school(school_progression: SchoolProgression, user: User) -> SchoolProgression:
    sp = SchoolProgression.objects.select_for_update().get(pk=school_progression.pk)
    if sp.to_school_academic_year_id_id:
        SchoolAcademicYear.objects.select_for_update().filter(
            pk=sp.to_school_academic_year_id_id
        ).first()
    allowed, reason = can_undo(sp)
    if not allowed:
        raise ConflictError(reason or "Undo is not allowed.", error_code="undo_not_allowed")

    now = timezone.now()
    logs = list(ProgressionRowLog.objects.filter(school_progression_id=sp))

    # 1. Soft-delete everything the progression created (mistakes, not history).
    created: dict[str, list[int]] = {}
    for entry in logs:
        if entry.action == "created":
            created.setdefault(entry.table, []).append(entry.row_id)
    for table, ids in created.items():
        MODELS[table]._default_manager.filter(pk__in=ids).update(
            is_active=False, removed=True, deleted_at=now, updated_at=now
        )

    # 2. Restore everything it archived.
    plain: dict[str, list[int]] = {}
    restore_removed: dict[str, list[int]] = {}
    reactivate: list[int] = []
    for entry in logs:
        if entry.action != "archived":
            continue
        if entry.meta.get("reactivate"):
            reactivate.append(entry.row_id)
        elif entry.meta.get("restore_removed"):
            restore_removed.setdefault(entry.table, []).append(entry.row_id)
        else:
            plain.setdefault(entry.table, []).append(entry.row_id)
    for table, ids in plain.items():
        MODELS[table]._default_manager.filter(pk__in=ids).update(is_active=True, updated_at=now)
    for table, ids in restore_removed.items():  # graduates' retired links
        MODELS[table]._default_manager.filter(pk__in=ids).update(
            is_active=True, removed=False, deleted_at=None, updated_at=now
        )
    if reactivate:
        Child.objects.filter(pk__in=reactivate).update(is_active=True, updated_at=now)

    sp.status = "undone"
    sp.undone_at = now
    sp.undone_by = user
    sp.save(update_fields=["status", "undone_at", "undone_by", "updated_at"])
    recompute_run_status(sp.run_id)
    return sp
