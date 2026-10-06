"""F-M10-7: Start a run and execute schools (one transaction each)."""

from datetime import date, time
from types import SimpleNamespace
from unittest.mock import patch

from django.test import Client

import pytest

from sessionops.exceptions import ConflictError, ValidationError
from sessionops.models import (
    AcademicYear,
    BatchChild,
    Child,
    ChildClass,
    ChildClassSection,
    ChildRemovalLog,
    Class,
    ClassSection,
    ClassSectionSubject,
    Partner,
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
    Subject,
)
from sessionops.services.progression.execute import execute_school
from sessionops.services.progression.freeze import is_school_frozen
from sessionops.services.progression.precheck import preview
from sessionops.services.progression.start import start_run
from sessionops.tests.exports.factories import active_year, auth_headers, make_school, make_user
from sessionops.tests.progression.test_f_m10_6_precheck_preview import School, _catalog, _year


@pytest.fixture
def ctx(db):
    admin = make_user("Function Lead")
    target = active_year(admin)  # 2026-27 active; schools below are on 2025-26
    return SimpleNamespace(admin=admin, target=target, catalog=_catalog())


def _timetable(s: School, section: ClassSection, volunteer):
    slot = Slot.objects.create(
        school_id=s.pid,
        school_academic_year_id=s.say,
        slot_name="Monday 10:00",
        day_of_week="monday",
        start_time=time(10),
        end_time=time(11),
        created_by=s.admin,
    )
    subject, _ = Subject.objects.get_or_create(
        subject_name="English", defaults={"program_id": s.catalog["5"].program_id}
    )
    css = ClassSectionSubject.objects.create(
        class_section_id=section, subject_id=subject, created_by=s.admin
    )
    scs = SlotClassSection.objects.create(
        slot_id=slot,
        class_section_id=section,
        class_section_subject_id=css,
        created_by=s.admin,
    )
    SlotClassSectionVolunteer.objects.create(
        slot_class_section_id=scs, volunteer_id=volunteer, created_by=s.admin
    )
    return slot


def _full_school(ctx):
    """5th–8th, two sections (one empty), children in every class, one with no section,
    a school volunteer, a staffed slot-class, a session and a holiday."""
    s = School(ctx.admin, ctx.catalog, name="Full")
    a, s.empty = s.section("Group A"), s.section("Group Empty")
    s.group = a
    s.kids = {code: [s.child(code, a, first=f"K{code}{i}") for i in range(2)] for code in "5678"}
    s.loose = s.child("6", None, first="NoSection")
    s.vol = make_user("Wingman")
    SchoolVolunteer.objects.create(
        school_id=s.pid,
        volunteer_id=s.vol,
        school_academic_year_id=s.say,
        created_by=ctx.admin,
    )
    s.slot = _timetable(s, a, s.vol)
    SchoolSessionDetails.objects.create(
        school_id=s.pid,
        school_academic_year=s.say,
        start_date=date(2025, 7, 1),
        end_date=date(2026, 3, 31),
        created_by=ctx.admin,
    )
    s.holiday = SchoolHoliday.objects.create(
        school_id=s.pid,
        school_academic_year_id=s.say,
        holiday_reason="holidays",
        start_date=date(2025, 10, 1),
        end_date=date(2025, 10, 2),
        created_by=ctx.admin,
    )
    return s


def _run(ctx, *schools, marks=None):
    marks = marks or {}
    payload = [
        {
            "school_id": s.pid,
            "graduate_class_ids": marks.get(s.pid, {}).get("classes", []),
            "graduate_child_ids": marks.get(s.pid, {}).get("children", []),
        }
        for s in schools
    ]
    return start_run(ctx.admin, payload)


def _current_class(child) -> str:
    cc = ChildClass.objects.get(child_id=child, is_active=True, removed=False)
    return cc.school_class_id.class_id.class_name


def _snapshot(school_id):
    """Every row (id, is_active, removed) of the tables progression touches."""
    tables = {
        "say": SchoolAcademicYear.objects.filter(school_id=school_id),
        "sc": SchoolClass.objects.filter(school_id=school_id),
        "cs": ClassSection.objects.filter(school_id=school_id),
        "cc": ChildClass.objects.filter(child_id__school_id=school_id),
        "ccs": ChildClassSection.objects.filter(child_id__school_id=school_id),
        "bc": BatchChild.objects.filter(school_id=school_id),
        "sv": SchoolVolunteer.objects.filter(school_id=school_id),
        "slot": Slot.objects.filter(school_id=school_id),
        "sess": SchoolSessionDetails.objects.filter(school_id=school_id),
        "child": Child.objects.filter(school_id=school_id),
    }
    return {k: sorted(qs.values_list("pk", "is_active", "removed")) for k, qs in tables.items()}


# ── Execute: the full map ──────────────────────────────────────────────────────


def test_execute_full_school(ctx):
    s = _full_school(ctx)
    run = _run(ctx, s)

    sp = execute_school(run, s.pid, ctx.admin)

    assert sp.status == "completed", sp.error
    # School-year swapped.
    new_say = SchoolAcademicYear.objects.get(school_id=s.pid, is_active=True, removed=False)
    assert new_say.academic_year_id == ctx.target
    assert not SchoolAcademicYear.objects.get(pk=s.say.pk).is_active
    # Classes copied into the new year.
    assert sorted(
        SchoolClass.objects.filter(school_academic_year_id=new_say).values_list(
            "class_id__class_name", flat=True
        )
    ) == ["5th", "6th", "7th", "8th"]
    # Children moved up; 8th stays.
    assert [_current_class(c) for c in s.kids["5"]] == ["6th", "6th"]
    assert [_current_class(c) for c in s.kids["7"]] == ["8th", "8th"]
    assert [_current_class(c) for c in s.kids["8"]] == ["8th", "8th"]
    # Sections copied (incl. the empty one), same names, no class link, new year.
    new_sections = ClassSection.objects.filter(school_academic_year_id=new_say)
    assert sorted(new_sections.values_list("section_display_name", flat=True)) == [
        "Group A",
        "Group Empty",
    ]
    assert not new_sections.filter(school_class_id__isnull=False).exists()
    new_a = new_sections.get(section_display_name="Group A")
    # Children remapped old section → new section.
    ccs = ChildClassSection.objects.get(child_id=s.kids["5"][0], is_active=True, removed=False)
    assert ccs.class_section_id == new_a
    assert not ClassSection.objects.get(pk=s.group.pk).is_active
    # The child with no section still has none.
    assert not ChildClassSection.objects.filter(child_id=s.loose, is_active=True).exists()
    # One BatchChild per child for the new year.
    assert BatchChild.objects.filter(school_academic_year_id=new_say, is_active=True).count() == 9
    # Volunteers carried; timetable + session archived; holiday untouched.
    assert (
        SchoolVolunteer.objects.filter(school_academic_year_id=new_say, is_active=True).count() == 1
    )
    assert not Slot.objects.get(pk=s.slot.pk).is_active
    assert not SlotClassSectionVolunteer.objects.filter(
        is_active=True, slot_class_section_id__slot_id=s.slot
    ).exists()
    assert not SchoolSessionDetails.objects.filter(school_id=s.pid, is_active=True).exists()
    holiday = SchoolHoliday.objects.get(pk=s.holiday.pk)
    assert holiday.is_active and holiday.school_academic_year_id_id == s.say.pk
    # Nothing deleted: archived rows are is_active=False, removed=False.
    assert not ClassSection.objects.filter(pk=s.group.pk, removed=True).exists()
    # Unfrozen afterwards; run completed.
    assert not is_school_frozen(s.pid)
    run.refresh_from_db()
    assert run.status == "completed"


def test_counts_equal_the_preview(ctx):
    s = _full_school(ctx)
    expected = preview([{"school_id": s.pid}])[0]["counts"]
    run = _run(ctx, s)

    sp = execute_school(run, s.pid, ctx.admin)

    assert sp.counts == expected


def test_row_log_records_every_created_and_archived_row(ctx):
    s = _full_school(ctx)
    run = _run(ctx, s)
    sp = execute_school(run, s.pid, ctx.admin)

    logs = ProgressionRowLog.objects.filter(school_progression_id=sp)
    created = {t for t in logs.filter(action="created").values_list("table", flat=True)}
    archived = {t for t in logs.filter(action="archived").values_list("table", flat=True)}

    assert {
        "school_academic_year",
        "school_class",
        "class_section",
        "child_class",
        "batch_child",
        "school_volunteer",
    } <= created
    assert {
        "slot",
        "slot_class_section",
        "slot_class_section_volunteer",
        "school_session_details",
    } <= archived
    remap = logs.get(table="class_section", action="created", source_row_id=s.group.pk)
    assert ClassSection.objects.get(pk=remap.row_id).section_display_name == "Group A"


# ── Graduation, 9th, empty/no-section ──────────────────────────────────────────


def test_graduation_retires_children_with_reason(ctx):
    s = _full_school(ctx)  # 8th children sit in a staffed bucket: no R-bucket error expected
    run = _run(ctx, s, marks={s.pid: {"classes": [ctx.catalog["8"].pk]}})

    sp = execute_school(run, s.pid, ctx.admin)

    assert sp.status == "completed", sp.error
    for child in s.kids["8"]:
        child.refresh_from_db()
        assert not child.is_active
        assert (
            ChildRemovalLog.objects.get(child_id=child, is_active=True).removed_reason
            == "graduated"
        )
        assert not ChildClass.objects.filter(child_id=child, is_active=True).exists()
    assert sp.counts["children_graduating"] == 2


def test_eighth_moves_to_new_ninth(ctx):
    nine = Class.objects.create(
        class_code="9",
        class_name="9th",
        sequence=9,
        program_id=ctx.catalog["5"].program_id,
    )
    Class.objects.filter(pk=ctx.catalog["8"].pk).update(next_class_id=nine)
    s = School(ctx.admin, ctx.catalog)
    kid = s.child("8", s.section())
    run = _run(ctx, s)

    execute_school(run, s.pid, ctx.admin)

    assert _current_class(kid) == "9th"


# ── Atomicity, retry, blockers, idempotency, isolation ─────────────────────────


def test_failure_rolls_back_everything_then_retry_succeeds(ctx):
    s = _full_school(ctx)
    run = _run(ctx, s)
    before = _snapshot(s.pid)

    with patch.object(SchoolVolunteer.objects, "bulk_create", side_effect=RuntimeError("boom")):
        sp = execute_school(run, s.pid, ctx.admin)

    assert sp.status == "failed"
    assert "boom" in sp.error
    assert _snapshot(s.pid) == before
    assert is_school_frozen(s.pid)

    retry = execute_school(run, s.pid, ctx.admin)
    assert retry.status == "completed", retry.error


def test_blocker_appearing_after_start_fails_without_writing(ctx):
    s = School(ctx.admin, ctx.catalog)
    kid = s.child("5", s.section())
    run = _run(ctx, s)
    ChildClass.objects.create(child_id=kid, school_class_id=s.classes["6"], created_by=ctx.admin)
    before = _snapshot(s.pid)

    sp = execute_school(run, s.pid, ctx.admin)

    assert sp.status == "failed"
    assert "CHILD_CLASS_CONFLICT" in sp.error
    assert _snapshot(s.pid) == before


def test_execute_is_idempotent_and_guards_other_states(ctx):
    s = School(ctx.admin, ctx.catalog)
    s.child("5", s.section())
    run = _run(ctx, s)
    first = execute_school(run, s.pid, ctx.admin)
    again = execute_school(run, s.pid, ctx.admin)
    assert (first.status, again.status) == ("completed", "completed")
    assert (
        SchoolAcademicYear.objects.filter(school_id=s.pid, academic_year_id=ctx.target).count() == 1
    )

    SchoolProgression.objects.filter(pk=first.pk).update(status="running")
    with pytest.raises(ConflictError):
        execute_school(run, s.pid, ctx.admin)


def test_other_schools_are_untouched(ctx):
    s = School(ctx.admin, ctx.catalog, name="Moves")
    s.child("5", s.section())
    other = School(ctx.admin, ctx.catalog, name="Stays")
    other.child("5", other.section())
    before = _snapshot(other.pid)
    run = _run(ctx, s)

    execute_school(run, s.pid, ctx.admin)

    assert _snapshot(other.pid) == before


# ── Start ──────────────────────────────────────────────────────────────────────


def test_start_freezes_selected_schools_and_rejects_blocked(ctx):
    s = School(ctx.admin, ctx.catalog)
    blocked = School(ctx.admin, ctx.catalog, name="Blocked")
    Partner.objects.filter(pk=blocked.partner.pk).update(converted=False)

    with pytest.raises(ValidationError, match="NOT_CONVERTED"):
        _run(ctx, blocked)
    assert not is_school_frozen(blocked.pid)  # rejected Start writes nothing

    run = _run(ctx, s)
    assert is_school_frozen(s.pid)
    assert run.cleanup["flipped"] is False  # 2026-27 already active: no flip


def test_start_flips_global_year_once_and_archives_non_converted(ctx):
    # Everyone on 2026-27 → target is the later 2027-28, and Start flips.
    s = School(ctx.admin, ctx.catalog)
    SchoolAcademicYear.objects.filter(pk=s.say.pk).update(academic_year_id=ctx.target)
    later = _year("2027-2028", ctx.admin)
    stray, _ = make_school(name="Not converted")
    Partner.objects.filter(pk=stray.pk).update(converted=False)
    stray_say = SchoolAcademicYear.objects.create(
        school_id=stray.partner_id, academic_year_id=ctx.target, created_by=ctx.admin
    )

    run = start_run(ctx.admin, [{"school_id": s.pid}])

    assert AcademicYear.objects.get(is_active=True) == later
    assert run.cleanup["flipped"] is True
    assert run.cleanup["archived_non_converted_say_ids"] == [stray_say.pk]
    assert not SchoolAcademicYear.objects.get(pk=stray_say.pk).is_active

    # A second run targets the now-active year and does not flip again.
    s2 = School(ctx.admin, ctx.catalog, name="Late")
    SchoolAcademicYear.objects.filter(pk=s2.say.pk).update(academic_year_id=ctx.target)
    run2 = start_run(ctx.admin, [{"school_id": s2.pid}])
    assert run2.cleanup["flipped"] is False
    assert AcademicYear.objects.filter(is_active=True).count() == 1


def test_one_run_moves_schools_from_different_years(ctx):
    """2025-26 → 2026-27 and 2026-27 → 2027-28 together; nobody waits for anybody."""
    behind = School(ctx.admin, ctx.catalog, name="Behind")  # 2025-26
    behind.child("5", behind.section())
    current = School(ctx.admin, ctx.catalog, name="Current")
    SchoolAcademicYear.objects.filter(pk=current.say.pk).update(academic_year_id=ctx.target)
    current.child("6", current.section())
    later = _year("2027-2028", ctx.admin)
    untouched = School(ctx.admin, ctx.catalog, name="Stays")  # not selected

    # One school per run: the straggler doesn't block the school moving to 2027-28.
    first = _run(ctx, current)
    assert first.cleanup["flipped"] is True  # 2027-28 becomes the active year
    assert AcademicYear.objects.get(is_active=True) == later
    assert execute_school(first, current.pid, ctx.admin).status == "completed"

    second = _run(ctx, behind)
    assert second.cleanup["flipped"] is False  # 2026-27 is older than the active year
    assert execute_school(second, behind.pid, ctx.admin).status == "completed"

    def year_of(s):
        return SchoolAcademicYear.objects.get(school_id=s.pid, is_active=True).academic_year_id

    assert year_of(behind) == ctx.target
    assert year_of(current) == later
    assert year_of(untouched).label == "2025-2026"  # unselected schools stay put


def test_start_rejects_more_than_one_school(ctx):
    a = School(ctx.admin, ctx.catalog, name="A")
    b = School(ctx.admin, ctx.catalog, name="B")
    with pytest.raises(ValidationError, match="one school at a time"):
        _run(ctx, a, b)
    assert not is_school_frozen(a.pid) and not is_school_frozen(b.pid)


# ── API ────────────────────────────────────────────────────────────────────────

BASE = "/api/admin/progression"


@pytest.fixture
def client():
    return Client()


def test_api_start_execute_and_read(client, ctx):
    s = School(ctx.admin, ctx.catalog)
    s.child("5", s.section())
    h = auth_headers(ctx.admin)

    resp = client.post(
        f"{BASE}/runs/",
        {"schools": [{"school_id": s.pid}]},
        content_type="application/json",
        **h,
    )
    assert resp.status_code == 201, resp.content
    run_id = resp.json()["run_id"]

    ex = client.post(f"{BASE}/runs/{run_id}/schools/{s.pid}/execute/", **h)
    assert ex.status_code == 200
    assert ex.json()["status"] == "completed"

    runs = client.get(f"{BASE}/runs/", **h).json()
    assert runs[0]["run_id"] == run_id and runs[0]["status"] == "completed"
    assert runs[0]["year_moves"] == [{"label": "2025-2026 → 2026-2027", "schools": 1}]

    detail = client.get(f"{BASE}/runs/{run_id}/", **h).json()
    assert [x["school_id"] for x in detail["schools"]] == [s.pid]

    school = client.get(f"{BASE}/runs/{run_id}/schools/{s.pid}/", **h).json()
    assert school["row_log"]["created"]["child_class"] == 1
    assert (school["from_year_label"], school["to_year_label"]) == ("2025-2026", "2026-2027")


def test_api_start_blocked_is_400_and_non_admin_403(client, ctx):
    s = School(ctx.admin, ctx.catalog)
    Partner.objects.filter(pk=s.partner.pk).update(converted=False)
    body = {"schools": [{"school_id": s.pid}]}

    assert (
        client.post(
            f"{BASE}/runs/",
            body,
            content_type="application/json",
            **auth_headers(ctx.admin),
        ).status_code
        == 400
    )
    co = make_user("CO Full Time")
    assert (
        client.post(
            f"{BASE}/runs/", body, content_type="application/json", **auth_headers(co)
        ).status_code
        == 403
    )
