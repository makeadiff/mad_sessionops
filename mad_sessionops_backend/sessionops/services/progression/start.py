"""F-M10-7: Start a progression run.

A run progresses exactly ONE school (2026-10-06: one at a time, so every move
is confirmed and reviewed on its own). One transaction:
1. validate graduation marks; re-precheck (any blocked → 400). Each school's
   target is the year after its own (services/progression/target.py);
2. if any target is later than the active year, make the newest target the
   active year (R8) — the platform follows the newest year in use;
3. archive active school-years of non-converted schools (cleanup, recorded);
4. create the run and one queued SchoolProgression per school, each with its own
   target year (→ frozen, F-M10-5).
"""

from django.db import transaction

from sessionops.exceptions import ValidationError
from sessionops.models import (
    AcademicYear,
    Partner,
    ProgressionRun,
    SchoolAcademicYear,
    SchoolProgression,
    User,
)
from sessionops.services.progression.freeze import frozen_school_ids
from sessionops.services.progression.planner import Marks, build_plans, validate_marks
from sessionops.services.progression.target import label_start


@transaction.atomic
def start_run(user: User, schools: list[dict]) -> ProgressionRun:
    if not schools:
        raise ValidationError("Select a school.")
    if len({s["school_id"] for s in schools}) > 1:
        raise ValidationError("Progress one school at a time.")

    marks: dict[int, Marks] = {}
    for s in schools:
        m = Marks(
            set(s.get("graduate_class_ids") or []),
            set(s.get("graduate_child_ids") or []),
        )
        validate_marks(s["school_id"], m)
        marks[s["school_id"]] = m
    ids = list(dict.fromkeys(s["school_id"] for s in schools))

    plans = build_plans(ids, marks, frozen_ids=frozen_school_ids())
    blocked = {sid: [b["code"] for b in p.blockers] for sid, p in plans.items() if p.blockers}
    if blocked:
        detail = "; ".join(f"{sid}: {', '.join(codes)}" for sid, codes in blocked.items())
        raise ValidationError(f"Blocked schools can't be started ({detail}).")

    # The active year follows the newest year any school moves into. Unblocked
    # plans always have a target year (no target → NO_NEXT_YEAR blocker above).
    targets = [p.to_year for p in plans.values() if p.to_year is not None]
    active = AcademicYear.objects.select_for_update().filter(is_active=True, removed=False).first()
    newest = max(targets, key=lambda y: label_start(str(y.label)))
    flipped = active is None or label_start(str(newest.label)) > label_start(str(active.label))
    if flipped:
        if active is not None:
            AcademicYear.objects.filter(pk=active.pk).update(is_active=False)
        AcademicYear.objects.filter(pk=int(newest.pk)).update(is_active=True)

    converted = Partner.objects.filter(converted=True).values_list("partner_id", flat=True)
    stale = SchoolAcademicYear.objects.filter(is_active=True, removed=False).exclude(
        school_id__in=converted
    )
    stale_ids = list(stale.values_list("pk", flat=True))
    stale.update(is_active=False, updated_by_id=user.user_id)

    run = ProgressionRun.objects.create(
        started_by=user,
        cleanup={
            "archived_non_converted_say_ids": stale_ids,
            "flipped": flipped,
            "activated_year_label": newest.label if flipped else None,
        },
    )
    # Unblocked plans always have an active school-year (else NO_ACTIVE_SCHOOL_YEAR).
    from_say = {
        sid: say_id
        for sid, p in plans.items()
        if (say_id := p.from_school_academic_year_id) is not None
    }
    SchoolProgression.objects.bulk_create(
        [
            SchoolProgression(
                run_id=run,
                school_id=sid,
                from_school_academic_year_id_id=from_say[sid],
                to_academic_year_id=plans[sid].to_year,
                graduate_class_ids=sorted(marks[sid].graduate_class_ids),
                graduate_child_ids=sorted(marks[sid].graduate_child_ids),
                warnings=[w["code"] for w in plans[sid].warnings],
            )
            for sid in ids
        ]
    )
    return run
