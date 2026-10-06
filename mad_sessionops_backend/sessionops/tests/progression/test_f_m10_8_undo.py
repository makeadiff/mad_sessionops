"""F-M10-8: per-school undo, driven by the row log, until the first new-year write."""

from datetime import date, time
from types import SimpleNamespace

from django.test import Client

import pytest

from sessionops.exceptions import ConflictError
from sessionops.models import (
    AcademicYear,
    BatchChild,
    Child,
    ChildClass,
    ChildClassSection,
    ChildProgram,
    ChildRemovalLog,
    ClassSection,
    SchoolAcademicYear,
    SchoolClass,
    SchoolHoliday,
    SchoolProgression,
    SchoolSessionDetails,
    SchoolVolunteer,
    Slot,
    SlotClassSection,
    SlotClassSectionVolunteer,
)
from sessionops.services.progression.execute import execute_school
from sessionops.services.progression.undo import can_undo, undo_school
from sessionops.tests.exports.factories import active_year, auth_headers, make_user
from sessionops.tests.progression.test_f_m10_6_precheck_preview import School, _catalog
from sessionops.tests.progression.test_f_m10_7_execute import _full_school, _run


@pytest.fixture
def ctx(db):
    admin = make_user("Function Lead")
    target = active_year(admin)  # 2026-27 active; schools are on 2025-26
    return SimpleNamespace(admin=admin, target=target, catalog=_catalog())


TABLES = {
    "say": lambda sid: SchoolAcademicYear.objects.filter(school_id=sid),
    "sc": lambda sid: SchoolClass.objects.filter(school_id=sid),
    "cs": lambda sid: ClassSection.objects.filter(school_id=sid),
    "child": lambda sid: Child.objects.filter(school_id=sid),
    "cc": lambda sid: ChildClass.objects.filter(child_id__school_id=sid),
    "ccs": lambda sid: ChildClassSection.objects.filter(child_id__school_id=sid),
    "bc": lambda sid: BatchChild.objects.filter(school_id=sid),
    "cp": lambda sid: ChildProgram.objects.filter(child_id__school_id=sid),
    "log": lambda sid: ChildRemovalLog.objects.filter(school_id=sid),
    "sv": lambda sid: SchoolVolunteer.objects.filter(school_id=sid),
    "slot": lambda sid: Slot.objects.filter(school_id=sid),
    "scs": lambda sid: SlotClassSection.objects.filter(slot_id__school_id=sid),
    "scsv": lambda sid: SlotClassSectionVolunteer.objects.filter(
        slot_class_section_id__slot_id__school_id=sid
    ),
    "sess": lambda sid: SchoolSessionDetails.objects.filter(school_id=sid),
}


def _state(sid) -> dict[str, dict[int, tuple]]:
    return {
        name: {pk: (a, r) for pk, a, r in q(sid).values_list("pk", "is_active", "removed")}
        for name, q in TABLES.items()
    }


def _progress(ctx, school, marks=None):
    run = _run(ctx, school, marks=marks)
    sp = execute_school(run, school.pid, ctx.admin)
    assert sp.status == "completed", sp.error
    return run, sp


# ── Snapshot restore ───────────────────────────────────────────────────────────


def test_undo_restores_every_pre_existing_row_and_soft_deletes_created_ones(ctx):
    s = _full_school(ctx)
    before = _state(s.pid)
    _, sp = _progress(ctx, s, marks={s.pid: {"classes": [ctx.catalog["8"].pk]}})

    undone = undo_school(sp, ctx.admin)

    assert undone.status == "undone"
    after = _state(s.pid)
    for table, rows in before.items():
        for pk, flags in rows.items():
            assert after[table][pk] == flags, (table, pk)
        for pk in set(after[table]) - set(rows):  # created by the run
            assert after[table][pk] == (False, True), (table, pk)
    # Back on the old year.
    assert (
        SchoolAcademicYear.objects.get(school_id=s.pid, is_active=True, removed=False).pk
        == s.say.pk
    )


def test_graduated_children_are_active_again(ctx):
    s = _full_school(ctx)
    _, sp = _progress(ctx, s, marks={s.pid: {"classes": [ctx.catalog["8"].pk]}})

    undo_school(sp, ctx.admin)

    for child in s.kids["8"]:
        child.refresh_from_db()
        assert child.is_active
        assert not ChildRemovalLog.objects.filter(
            child_id=child, removed_reason="graduated", is_active=True
        ).exists()


def test_undo_keeps_global_year(ctx):
    s = School(ctx.admin, ctx.catalog)
    s.child("5", s.section())
    _, sp = _progress(ctx, s)

    undo_school(sp, ctx.admin)

    assert AcademicYear.objects.get(is_active=True) == ctx.target


def test_undone_school_can_be_progressed_again(ctx):
    s = School(ctx.admin, ctx.catalog)
    kid = s.child("5", s.section())
    _, sp = _progress(ctx, s)
    undo_school(sp, ctx.admin)

    _, again = _progress(ctx, s)

    assert again.status == "completed"
    cc = ChildClass.objects.get(child_id=kid, is_active=True, removed=False)
    assert cc.school_class_id.class_id.class_name == "6th"
    assert SchoolAcademicYear.objects.filter(school_id=s.pid, is_active=True).count() == 1


# ── Undo is blocked by new-year writes ─────────────────────────────────────────


def _new_say(sp):
    sp.refresh_from_db()
    return sp.to_school_academic_year_id


def test_can_undo_right_after_completion(ctx):
    s = School(ctx.admin, ctx.catalog)
    s.child("5", s.section())
    _, sp = _progress(ctx, s)
    assert can_undo(sp) == (True, None)


@pytest.mark.parametrize("write", ["slot", "bucket", "session", "holiday", "enrol", "edit"])
def test_new_year_write_blocks_undo(ctx, write):
    s = School(ctx.admin, ctx.catalog)
    s.child("5", s.section())
    _, sp = _progress(ctx, s)
    say = _new_say(sp)
    admin = ctx.admin
    if write == "slot":
        Slot.objects.create(
            school_id=s.pid,
            school_academic_year_id=say,
            slot_name="New",
            day_of_week="friday",
            start_time=time(9),
            end_time=time(10),
            created_by=admin,
        )
    elif write == "bucket":
        ClassSection.objects.create(
            school_id=s.pid,
            section_name="fresh",
            school_academic_year_id=say,
            created_by=admin,
        )
    elif write == "session":
        SchoolSessionDetails.objects.create(
            school_id=s.pid,
            school_academic_year=say,
            start_date=date(2026, 7, 1),
            end_date=date(2027, 3, 31),
            created_by=admin,
        )
    elif write == "holiday":
        SchoolHoliday.objects.create(
            school_id=s.pid,
            school_academic_year_id=say,
            holiday_reason="holidays",
            start_date=date(2026, 8, 15),
            end_date=date(2026, 8, 15),
            created_by=admin,
        )
    elif write == "enrol":
        Child.objects.create(
            school_id=s.pid,
            first_name="New",
            last_name="Kid",
            gender="male",
            age=9,
            created_by=admin,
        )
    else:  # an edit to a row the run created
        section = ClassSection.objects.get(school_academic_year_id=say)
        section.section_display_name = "Renamed"
        section.save()

    allowed, reason = can_undo(sp)

    assert not allowed and reason
    with pytest.raises(ConflictError) as exc:
        undo_school(sp, admin)
    assert exc.value.error_code == "undo_not_allowed"


@pytest.mark.parametrize("status", ["undone", "failed", "queued"])
def test_undo_requires_completed(ctx, status):
    s = School(ctx.admin, ctx.catalog)
    s.child("5", s.section())
    _, sp = _progress(ctx, s)
    SchoolProgression.objects.filter(pk=sp.pk).update(status=status)
    sp.refresh_from_db()

    with pytest.raises(ConflictError):
        undo_school(sp, ctx.admin)


# ── API ────────────────────────────────────────────────────────────────────────

BASE = "/api/admin/progression"


@pytest.fixture
def client():
    return Client()


def test_api_undo_and_can_undo_flag(client, ctx):
    s = School(ctx.admin, ctx.catalog)
    s.child("5", s.section())
    run, sp = _progress(ctx, s)
    h = auth_headers(ctx.admin)

    row = client.get(f"{BASE}/runs/{run.pk}/", **h).json()["schools"][0]
    assert (row["can_undo"], row["undo_block_reason"]) == (True, None)

    assert (
        client.post(
            f"{BASE}/runs/{run.pk}/schools/{s.pid}/undo/",
            **auth_headers(make_user("CO Full Time")),
        ).status_code
        == 403
    )
    resp = client.post(f"{BASE}/runs/{run.pk}/schools/{s.pid}/undo/", **h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "undone"

    again = client.post(f"{BASE}/runs/{run.pk}/schools/{s.pid}/undo/", **h)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "undo_not_allowed"


def test_api_can_undo_false_with_reason_after_new_year_write(client, ctx):
    s = School(ctx.admin, ctx.catalog)
    s.child("5", s.section())
    run, sp = _progress(ctx, s)
    Slot.objects.create(
        school_id=s.pid,
        school_academic_year_id=_new_say(sp),
        slot_name="New",
        day_of_week="friday",
        start_time=time(9),
        end_time=time(10),
        created_by=ctx.admin,
    )

    row = client.get(f"{BASE}/runs/{run.pk}/", **auth_headers(ctx.admin)).json()["schools"][0]

    assert row["can_undo"] is False
    assert "slot" in row["undo_block_reason"].lower()
