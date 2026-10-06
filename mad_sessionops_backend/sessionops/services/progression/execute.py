"""F-M10-7: execute one school's progression — one transaction, all or nothing.

Applies exactly the F-M10-6 planner's SchoolPlan (re-built inside the lock, so data
that changed since the preview can't slip through):

 1. lock the school's active school-year (syncs that need it wait here)
 2. re-plan; blockers → school fails, nothing written
 3. archive old school-year, create the target one
 4. SchoolClass: copy offerings + add classes promoted children need
 5. ClassSection: archive old first (slug constraint is on active rows), copy with
    same names, no class link, new school-year → old→new id map
 6. children: graduates retired (reason "graduated"); others archived + re-created
    in the next (or same) class and the mapped section, with a new BatchChild
 7. SchoolVolunteer carried to the new school-year
 8. archive the old year's timetable, subjects and session
 9. log every created/archived row
10. mark completed with the counts

Any exception rolls the school back entirely; it is then marked failed (still
frozen) in a separate transaction and can be retried.
"""

from django.db import models, transaction
from django.utils import timezone

import sentry_sdk

from sessionops.exceptions import ConflictError
from sessionops.models import (
    BatchChild,
    Child,
    ChildClass,
    ChildClassSection,
    ChildSubject,
    ClassSection,
    ClassSectionSubject,
    SchoolAcademicYear,
    SchoolClass,
    SchoolProgression,
    SchoolSessionDetails,
    SchoolVolunteer,
    Slot,
    SlotClassSection,
    SlotClassSectionVolunteer,
)
from sessionops.services.children.deactivate import retire_child
from sessionops.services.progression.freeze import recompute_run_status
from sessionops.services.progression.planner import Marks, build_plans
from sessionops.services.progression.rowlog import RowLog

_ARCHIVE_MODELS: dict[str, type[models.Model]] = {
    "school_class": SchoolClass,
    "class_section": ClassSection,
    "child_class": ChildClass,
    "child_class_section": ChildClassSection,
    "batch_child": BatchChild,
    "school_volunteer": SchoolVolunteer,
    "slot": Slot,
    "slot_class_section": SlotClassSection,
    "slot_class_section_volunteer": SlotClassSectionVolunteer,
    "class_section_subject": ClassSectionSubject,
    "child_subject": ChildSubject,
    "school_session_details": SchoolSessionDetails,
}


class ProgressionBlocked(Exception):
    def __init__(self, blockers: list[dict]):
        self.blockers = blockers
        super().__init__("; ".join(f"{b['code']}: {b['message']}" for b in blockers))


def _archive(table: str, ids: list[int], user, now, log: RowLog) -> None:
    if not ids:
        return
    _ARCHIVE_MODELS[table]._default_manager.filter(pk__in=ids).update(
        is_active=False, updated_by_id=user.user_id, updated_at=now
    )
    log.archived(table, ids)


def execute_school(run, school_id: int, user) -> SchoolProgression:
    """Progress one queued (or failed → retry) school of `run`. Idempotent for
    completed schools; 409 while running (e.g. another tab) or after undo/release."""
    with transaction.atomic():
        sp = SchoolProgression.objects.select_for_update().get(run_id=run, school_id=school_id)
        if sp.status == "completed":
            return sp
        if sp.status != "queued" and sp.status != "failed":
            raise ConflictError(
                f"School {school_id} is {sp.status} and can't be executed.",
                error_code="execute_not_allowed",
            )
        sp.status = "running"
        sp.started_at = timezone.now()
        sp.error = None
        sp.save(update_fields=["status", "started_at", "error", "updated_at"])

    try:
        with transaction.atomic():
            counts = _apply(run, sp, user)
    except Exception as exc:  # roll back the school, then record the failure
        if not isinstance(exc, ProgressionBlocked):
            sentry_sdk.capture_exception(exc)
        with transaction.atomic():
            SchoolProgression.objects.filter(pk=sp.pk).update(
                status="failed", error=str(exc)[:2000], finished_at=timezone.now()
            )
            recompute_run_status(run)
        sp.refresh_from_db()
        return sp

    with transaction.atomic():
        SchoolProgression.objects.filter(pk=sp.pk).update(
            status="completed", counts=counts, finished_at=timezone.now()
        )
        recompute_run_status(run)
    sp.refresh_from_db()
    return sp


def _apply(run, sp: SchoolProgression, user) -> dict:
    now = timezone.now()
    # Fixed at Start (the year after the school's own); legacy runs had one per run.
    target_year = sp.to_academic_year_id or run.to_academic_year_id
    actor = run.started_by

    # 1. Lock the school's active school-year.
    old_say = (
        SchoolAcademicYear.objects.select_for_update()
        .filter(school_id=sp.school_id, is_active=True, removed=False)
        .first()
    )

    # 2. Re-plan inside the lock (own school isn't "already in a run" here).
    marks = {sp.school_id: Marks(set(sp.graduate_class_ids), set(sp.graduate_child_ids))}
    plan = build_plans(
        [sp.school_id], marks, frozen_ids=set(), targets={sp.school_id: target_year}
    )[sp.school_id]
    if plan.blockers or old_say is None:
        raise ProgressionBlocked(
            plan.blockers or [{"code": "NO_ACTIVE_SCHOOL_YEAR", "message": ""}]
        )

    log = RowLog(sp)

    # 3. School-year: archive old, then create the target one (one active per school).
    SchoolAcademicYear.objects.filter(pk=old_say.pk).update(
        is_active=False, updated_by_id=actor.user_id, updated_at=now
    )
    log.archived("school_academic_year", [old_say.pk])
    new_say = SchoolAcademicYear.objects.create(
        school_id=sp.school_id, academic_year_id=target_year, created_by=actor
    )
    log.created("school_academic_year", new_say.pk, old_say.pk)

    # 4. SchoolClass.
    _archive("school_class", plan.archive["school_class"], actor, now, log)
    new_classes = SchoolClass.objects.bulk_create(
        [
            SchoolClass(
                school_id=sp.school_id,
                school_academic_year_id=new_say,
                class_id_id=c.class_id,
                created_by=actor,
            )
            for c in plan.school_classes
        ]
    )
    class_map: dict[int, int] = {}
    for class_copy, class_row in zip(plan.school_classes, new_classes):
        class_map[class_copy.class_id] = class_row.pk
        log.created("school_class", class_row.pk, class_copy.source_school_class_id)

    # 5. ClassSection: archive first, then copy.
    _archive("class_section", plan.archive["class_section"], actor, now, log)
    new_sections = ClassSection.objects.bulk_create(
        [
            ClassSection(
                school_id=sp.school_id,
                school_class_id=None,
                section_code=None,
                section_name=s.section_name,
                section_display_name=s.section_display_name,
                school_academic_year_id=new_say,
                created_by=actor,
            )
            for s in plan.sections
        ]
    )
    section_map: dict[int, int] = {}
    for section_copy, section_row in zip(plan.sections, new_sections):
        section_map[section_copy.source_class_section_id] = section_row.pk
        log.created("class_section", section_row.pk, section_copy.source_class_section_id)

    # 6. Children.
    for table in ("child_class", "child_class_section", "batch_child"):
        _archive(table, plan.archive[table], actor, now, log)
    graduates = [m for m in plan.children if m.to_class_id is None]
    movers = [m for m in plan.children if m.to_class_id is not None]
    # child -> catalog class it moves into (movers only, so never None).
    target_class = {m.child_id: t for m in plan.children if (t := m.to_class_id) is not None}
    children_by_id = Child.objects.in_bulk([m.child_id for m in graduates])
    for move in graduates:
        retired = retire_child(
            children_by_id[move.child_id],
            reason="graduated",
            other_details="Graduated at year progression",
            user=actor,
            now=now,
        )
        log.archived("child", [move.child_id], reactivate=True)
        for table in (
            "child_class",
            "child_class_section",
            "batch_child",
            "child_program",
        ):
            log.archived(table, retired[table], restore_removed=True)
        log.created("child_removal_log", retired["child_removal_log"], move.child_id)

    new_child_classes = ChildClass.objects.bulk_create(
        [
            ChildClass(
                child_id_id=m.child_id,
                school_class_id_id=class_map[target_class[m.child_id]],
                created_by=actor,
            )
            for m in movers
        ]
    )
    for move, cc_row in zip(movers, new_child_classes):
        log.created("child_class", cc_row.pk, move.source_child_class_id)
    placed = [m for m in movers if m.source_section_id is not None]
    source_section = {m.child_id: sec for m in placed if (sec := m.source_section_id) is not None}
    new_ccs = ChildClassSection.objects.bulk_create(
        [
            ChildClassSection(
                child_id_id=m.child_id,
                class_section_id_id=section_map[source_section[m.child_id]],
                created_by=actor,
            )
            for m in placed
        ]
    )
    for move, ccs_row in zip(placed, new_ccs):
        log.created("child_class_section", ccs_row.pk, move.source_section_id)
    new_batch = BatchChild.objects.bulk_create(
        [
            BatchChild(
                child_id_id=m.child_id,
                school_id=sp.school_id,
                school_academic_year_id=new_say,
                created_by=actor,
            )
            for m in movers
        ]
    )
    for move, batch_row in zip(movers, new_batch):
        log.created("batch_child", batch_row.pk, move.child_id)

    # 7. SchoolVolunteer carried over.
    old_svs = list(SchoolVolunteer.objects.filter(pk__in=plan.volunteer_ids))
    _archive("school_volunteer", plan.archive["school_volunteer"], actor, now, log)
    new_svs = SchoolVolunteer.objects.bulk_create(
        [
            SchoolVolunteer(
                school_id=sp.school_id,
                volunteer_id_id=sv.volunteer_id_id,
                school_academic_year_id=new_say,
                created_by=actor,
            )
            for sv in old_svs
        ]
    )
    for old, sv_row in zip(old_svs, new_svs):
        log.created("school_volunteer", sv_row.pk, old.pk)

    # 8. Archive the old year's timetable, subjects and session.
    for table in (
        "slot_class_section_volunteer",
        "slot_class_section",
        "slot",
        "child_subject",
        "class_section_subject",
        "school_session_details",
    ):
        _archive(table, plan.archive[table], actor, now, log)

    # 9. Log. 10. Counts (the preview's, by construction).
    log.flush()
    SchoolProgression.objects.filter(pk=sp.pk).update(to_school_academic_year_id=new_say)
    return plan.counts
