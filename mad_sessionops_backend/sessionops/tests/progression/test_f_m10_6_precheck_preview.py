"""F-M10-6: per-school target year, planner (blockers, warnings, mapping, graduation), API."""

import importlib
from datetime import date, time
from types import SimpleNamespace

from django.apps import apps as django_apps
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

import pytest

from sessionops.models import (
    AcademicYear,
    BatchChild,
    Child,
    ChildClass,
    ChildClassSection,
    Class,
    ClassSection,
    Partner,
    Program,
    SchoolAcademicYear,
    SchoolClass,
    SchoolSessionDetails,
    SchoolVolunteer,
    Slot,
)
from sessionops.services.progression.planner import Marks, build_plans
from sessionops.tests.exports.factories import active_year, auth_headers, make_school, make_user

seed = importlib.import_module("sessionops.migrations.0033_seed_class_catalog")
_EDITOR = SimpleNamespace(connection=SimpleNamespace(alias="default"))


# ── Fixture helpers ────────────────────────────────────────────────────────────


def _catalog():
    program, _ = Program.objects.get_or_create(
        program_id=1, defaults={"program_name": "Foundation Program", "is_active": True}
    )
    for code in ("5", "6", "7", "8"):
        Class.objects.get_or_create(
            class_code=code, defaults={"class_name": f"{code}th", "program_id": program}
        )
    seed.seed(django_apps, _EDITOR)
    return {c.class_code: c for c in Class.objects.all()}


def _year(label, admin, active=False):
    year, _ = AcademicYear.objects.get_or_create(
        label=label, defaults={"is_active": active, "created_by": admin}
    )
    return year


class School:
    """A school on 2025-26 (its only active school-year) with classes and children."""

    def __init__(self, admin, catalog, offers=("5", "6", "7", "8"), name="Test School"):
        self.admin = admin
        self.catalog = catalog
        self.partner, _ = make_school(name=name)
        self.pid = self.partner.partner_id
        self.say = SchoolAcademicYear.objects.create(
            school_id=self.pid,
            academic_year_id=_year("2025-2026", admin),
            created_by=admin,
        )
        self.classes = {
            code: SchoolClass.objects.create(
                school_id=self.pid,
                school_academic_year_id=self.say,
                class_id=catalog[code],
                created_by=admin,
            )
            for code in offers
        }

    def section(self, name="Group A"):
        return ClassSection.objects.create(
            school_id=self.pid,
            section_name=name.lower().replace(" ", "_"),
            section_display_name=name,
            school_academic_year_id=self.say,
            created_by=self.admin,
        )

    def child(self, code, section=None, first="Kid"):
        child = Child.objects.create(
            school_id=self.pid,
            first_name=first,
            last_name="X",
            gender="female",
            age=10,
            created_by=self.admin,
        )
        ChildClass.objects.create(
            child_id=child, school_class_id=self.classes[code], created_by=self.admin
        )
        if section is not None:
            ChildClassSection.objects.create(
                child_id=child, class_section_id=section, created_by=self.admin
            )
        BatchChild.objects.create(
            child_id=child,
            school_id=self.pid,
            school_academic_year_id=self.say,
            created_by=self.admin,
        )
        return child


@pytest.fixture
def ctx(db):
    admin = make_user("Function Lead")
    target = active_year(admin)  # 2026-27, globally active
    catalog = _catalog()
    return SimpleNamespace(admin=admin, target=target, catalog=catalog)


def _plan(ctx, school, marks=None, frozen=None, targets=None):
    return build_plans([school.pid], marks, frozen_ids=frozen, targets=targets)[school.pid]


def _codes(items):
    return {i["code"] for i in items}


# ── Target year: each school moves to the year after its own ──────────────────


def _on(school, year):
    SchoolAcademicYear.objects.filter(pk=school.say.pk).update(academic_year_id=year)


def test_each_school_targets_the_year_after_its_own(ctx):
    behind = School(ctx.admin, ctx.catalog, name="Behind")  # 2025-26
    current = School(ctx.admin, ctx.catalog, name="Current")
    _on(current, ctx.target)  # 2026-27
    nxt = _year("2027-2028", ctx.admin)

    plans = build_plans([behind.pid, current.pid])

    assert plans[behind.pid].to_year == ctx.target
    assert plans[current.pid].to_year == nxt
    assert plans[behind.pid].blockers == plans[current.pid].blockers == []


def test_no_next_year_blocks_only_that_school(ctx):
    behind = School(ctx.admin, ctx.catalog, name="Behind")
    current = School(ctx.admin, ctx.catalog, name="Current")
    _on(current, ctx.target)  # 2027-28 doesn't exist

    plans = build_plans([behind.pid, current.pid])

    assert plans[behind.pid].blockers == []
    assert _codes(plans[current.pid].blockers) == {"NO_NEXT_YEAR"}
    assert "2027-2028" in plans[current.pid].blockers[0]["message"]
    assert plans[current.pid].to_year_label == "2027-2028"


def test_still_behind_warning_when_two_years_back(ctx):
    s = School(ctx.admin, ctx.catalog)
    _on(s, _year("2024-2025", ctx.admin))  # active is 2026-27

    plan = _plan(ctx, s)

    assert plan.to_year.label == "2025-2026"  # one step, no skipping
    warning = next(w for w in plan.warnings if w["code"] == "STILL_BEHIND")
    assert warning["n"] == 1 and warning["active"] == "2026-2027"


def test_one_year_behind_has_no_still_behind_warning(ctx):
    s = School(ctx.admin, ctx.catalog)  # 2025-26 → 2026-27 (active) catches up
    assert "STILL_BEHIND" not in _codes(_plan(ctx, s).warnings)


# ── Mapping ────────────────────────────────────────────────────────────────────


def test_mapping_moves_each_class_up_and_8th_stays(ctx):
    s = School(ctx.admin, ctx.catalog)
    g = s.section()
    for code, n in (("5", 2), ("6", 1), ("7", 3), ("8", 2)):
        for _ in range(n):
            s.child(code, g)

    plan = _plan(ctx, s)

    assert plan.counts["children_moving"] == [
        {"from": "5th", "to": "6th", "n": 2},
        {"from": "6th", "to": "7th", "n": 1},
        {"from": "7th", "to": "8th", "n": 3},
    ]
    assert plan.counts["children_staying"] == [{"class": "8th", "n": 2}]
    assert plan.counts["children_graduating"] == 0
    assert plan.counts["school_classes_copied"] == 4
    assert plan.counts["school_classes_added"] == []
    assert plan.counts["sections_copied"] == 1


def test_class_added_when_promoted_children_need_it(ctx):
    s = School(ctx.admin, ctx.catalog, offers=("5", "6", "7"))
    s.child("7", s.section())

    plan = _plan(ctx, s)

    assert plan.counts["school_classes_added"] == ["8th"]
    assert [c.class_name for c in plan.school_classes if c.source_school_class_id is None] == [
        "8th"
    ]


def test_ninth_added_and_8th_moves_to_it(ctx):
    nine = Class.objects.create(
        class_code="9",
        class_name="9th",
        sequence=9,
        program_id=ctx.catalog["5"].program_id,
    )
    Class.objects.filter(pk=ctx.catalog["8"].pk).update(next_class_id=nine)
    s = School(ctx.admin, ctx.catalog)
    s.child("8", s.section())

    plan = _plan(ctx, s)

    assert plan.counts["children_moving"] == [{"from": "8th", "to": "9th", "n": 1}]
    assert plan.counts["school_classes_added"] == ["9th"]


def test_empty_sections_are_copied_too(ctx):
    s = School(ctx.admin, ctx.catalog)
    s.section("Group A")
    s.section("Group B")
    assert _plan(ctx, s).counts["sections_copied"] == 2


def test_graduation_by_class_and_child_counts_once(ctx):
    s = School(ctx.admin, ctx.catalog)
    g = s.section()
    eighth = [s.child("8", g) for _ in range(3)]
    s.child("7", g)
    marks = {s.pid: Marks({ctx.catalog["8"].pk}, {eighth[0].pk})}

    plan = _plan(ctx, s, marks)

    assert plan.counts["children_graduating"] == 3
    assert plan.counts["children_staying"] == []
    assert [m.to_class_id for m in plan.children if m.child_id in {c.pk for c in eighth}] == [
        None
    ] * 3
    # Graduates' links aren't in the archive lists (retired like a deactivation).
    assert len(plan.archive["child_class"]) == 1


def test_archive_lists_cover_the_old_year(ctx):
    s = School(ctx.admin, ctx.catalog)
    g = s.section()
    s.child("5", g)
    Slot.objects.create(
        school_id=s.pid,
        school_academic_year_id=s.say,
        slot_name="Mon",
        day_of_week="monday",
        start_time=time(10),
        end_time=time(11),
        created_by=ctx.admin,
    )
    SchoolSessionDetails.objects.create(
        school_id=s.pid,
        school_academic_year=s.say,
        start_date=date(2025, 7, 1),
        end_date=date(2026, 3, 31),
        created_by=ctx.admin,
    )
    vol = make_user("Wingman")
    SchoolVolunteer.objects.create(
        school_id=s.pid,
        volunteer_id=vol,
        school_academic_year_id=s.say,
        created_by=ctx.admin,
    )

    counts = _plan(ctx, s).counts["archive_counts"]

    assert counts["school_class"] == 4
    assert counts["class_section"] == 1
    assert counts["child_class"] == counts["child_class_section"] == counts["batch_child"] == 1
    assert counts["slot"] == 1
    assert counts["school_session_details"] == 1
    assert counts["school_volunteer"] == 1


# ── Blockers ───────────────────────────────────────────────────────────────────


def test_clean_school_has_no_blockers(ctx):
    s = School(ctx.admin, ctx.catalog)
    s.child("5", s.section())
    plan = _plan(ctx, s)
    assert plan.blockers == []
    assert plan.status in ("ready", "warning")


def test_blocker_not_converted(ctx):
    s = School(ctx.admin, ctx.catalog)
    Partner.objects.filter(pk=s.partner.pk).update(converted=False)
    assert "NOT_CONVERTED" in _codes(_plan(ctx, s).blockers)


def test_blocker_pinned_target_no_longer_next(ctx):
    """Execution pins the year fixed at Start; if the school moved meanwhile, block."""
    s = School(ctx.admin, ctx.catalog)
    _on(s, ctx.target)
    plan = _plan(ctx, s, targets={s.pid: ctx.target})
    assert "TARGET_NOT_LATER" in _codes(plan.blockers)


def test_blocker_no_active_school_year(ctx):
    s = School(ctx.admin, ctx.catalog)
    SchoolAcademicYear.objects.filter(pk=s.say.pk).update(is_active=False)
    assert _codes(_plan(ctx, s).blockers) == {"NO_ACTIVE_SCHOOL_YEAR"}


def test_blocker_child_class_conflict(ctx):
    s = School(ctx.admin, ctx.catalog)
    child = s.child("5", s.section())
    ChildClass.objects.create(child_id=child, school_class_id=s.classes["6"], created_by=ctx.admin)
    assert "CHILD_CLASS_CONFLICT" in _codes(_plan(ctx, s).blockers)


def test_blocker_child_with_no_class(ctx):
    s = School(ctx.admin, ctx.catalog)
    Child.objects.create(
        school_id=s.pid,
        first_name="Lost",
        last_name="X",
        gender="male",
        age=9,
        created_by=ctx.admin,
    )
    assert "CHILD_CLASS_CONFLICT" in _codes(_plan(ctx, s).blockers)


def test_blocker_child_section_conflict(ctx):
    s = School(ctx.admin, ctx.catalog)
    child = s.child("5", s.section("Group A"))
    ChildClassSection.objects.create(
        child_id=child, class_section_id=s.section("Group B"), created_by=ctx.admin
    )
    assert "CHILD_SECTION_CONFLICT" in _codes(_plan(ctx, s).blockers)


def test_blocker_next_class_inactive(ctx):
    s = School(ctx.admin, ctx.catalog)
    s.child("5", s.section())
    Class.objects.filter(pk=ctx.catalog["6"].pk).update(is_active=False)
    assert "NEXT_CLASS_INACTIVE" in _codes(_plan(ctx, s).blockers)


def test_blocker_already_in_run(ctx):
    s = School(ctx.admin, ctx.catalog)
    plan = _plan(ctx, s, frozen={s.pid})
    assert "ALREADY_IN_RUN" in _codes(plan.blockers)
    assert plan.status == "blocked"


# ── Warnings ───────────────────────────────────────────────────────────────────


def test_warnings_no_next_class_no_section_closed_target(ctx):
    s = School(ctx.admin, ctx.catalog)
    s.child("8", s.section())  # stays: NO_NEXT_CLASS
    s.child("7")  # no section; 7 → 8, which is closed: CLASS_CLOSED_TARGET + CHILD_NO_SECTION

    codes = _codes(_plan(ctx, s).warnings)

    assert {"NO_NEXT_CLASS", "CHILD_NO_SECTION", "CLASS_CLOSED_TARGET"} <= codes


def test_warning_legacy_rows(ctx):
    s = School(ctx.admin, ctx.catalog)
    legacy = s.section("Old circle")
    ClassSection.objects.filter(pk=legacy.pk).update(school_academic_year_id=None)

    plan = _plan(ctx, s)

    assert "LEGACY_NO_SCHOOL_YEAR" in _codes(plan.warnings)
    assert plan.counts["sections_copied"] == 1  # legacy section is copied, not lost


def test_warnings_timetable_and_session(ctx):
    s = School(ctx.admin, ctx.catalog)
    Slot.objects.create(
        school_id=s.pid,
        school_academic_year_id=s.say,
        slot_name="Mon",
        day_of_week="monday",
        start_time=time(10),
        end_time=time(11),
        created_by=ctx.admin,
    )
    SchoolSessionDetails.objects.create(
        school_id=s.pid,
        school_academic_year=s.say,
        start_date=date(2025, 7, 1),
        end_date=date(2026, 3, 31),
        created_by=ctx.admin,
    )
    assert {"ACTIVE_TIMETABLE", "ACTIVE_SESSION"} <= _codes(_plan(ctx, s).warnings)


# ── Read-only + query count ────────────────────────────────────────────────────


def _row_counts():
    return {
        m.__name__: m.objects.count()
        for m in (
            SchoolAcademicYear,
            SchoolClass,
            ClassSection,
            Child,
            ChildClass,
            ChildClassSection,
            BatchChild,
        )
    }


def test_planner_is_read_only(ctx):
    s = School(ctx.admin, ctx.catalog)
    s.child("5", s.section())
    before = _row_counts()
    build_plans([s.pid], {s.pid: Marks({ctx.catalog["5"].pk}, set())})
    assert _row_counts() == before


def test_query_count_is_constant(ctx):
    first = School(ctx.admin, ctx.catalog, name="A")
    first.child("5", first.section())
    with CaptureQueriesContext(connection) as one:
        build_plans([first.pid])

    ids = [first.pid]
    for i in range(4):
        s = School(ctx.admin, ctx.catalog, name=f"S{i}")
        g = s.section()
        for code in ("5", "6", "7", "8"):
            for _ in range(5):
                s.child(code, g)
        ids.append(s.pid)
    with CaptureQueriesContext(connection) as many:
        build_plans(ids)

    assert len(many.captured_queries) == len(one.captured_queries)


# ── API ────────────────────────────────────────────────────────────────────────

BASE = "/api/admin/progression"


@pytest.fixture
def client():
    return Client()


def test_api_eligible_schools(client, ctx):
    behind = School(ctx.admin, ctx.catalog, name="Behind")
    caught_up, _ = make_school(name="Caught up")
    SchoolAcademicYear.objects.create(
        school_id=caught_up.partner_id,
        academic_year_id=ctx.target,
        created_by=ctx.admin,
    )

    body = client.get(f"{BASE}/eligible-schools/", **auth_headers(ctx.admin)).json()

    assert body["active_year_label"] == "2026-2027"
    by_name = {r["school_name"]: r for r in body["schools"]}
    behind_row = by_name["Behind"]
    assert behind_row["eligible"] is True
    assert behind_row["school_id"] == behind.pid
    assert (behind_row["current_year_label"], behind_row["target_year_label"]) == (
        "2025-2026",
        "2026-2027",
    )
    assert behind_row["years_behind"] == 1
    # On the active year with no 2027-28 yet: blocked, but it doesn't block "Behind".
    assert (by_name["Caught up"]["eligible"], by_name["Caught up"]["reason"]) == (
        False,
        "NO_NEXT_YEAR",
    )

    _year("2027-2028", ctx.admin)
    body = client.get(f"{BASE}/eligible-schools/", **auth_headers(ctx.admin)).json()
    caught = {r["school_name"]: r for r in body["schools"]}["Caught up"]
    assert (caught["eligible"], caught["target_year_label"]) == (True, "2027-2028")


def test_api_precheck_and_preview(client, ctx):
    s = School(ctx.admin, ctx.catalog)
    s.child("5", s.section())

    pre = client.post(
        f"{BASE}/precheck/",
        {"school_ids": [s.pid]},
        content_type="application/json",
        **auth_headers(ctx.admin),
    )
    assert pre.status_code == 200
    assert pre.json()[0]["target_year_label"] == "2026-2027"
    assert pre.json()[0]["status"] in ("ready", "warning")

    prev = client.post(
        f"{BASE}/preview/",
        {"schools": [{"school_id": s.pid}]},
        content_type="application/json",
        **auth_headers(ctx.admin),
    )
    assert prev.status_code == 200
    assert prev.json()[0]["counts"]["children_moving"] == [{"from": "5th", "to": "6th", "n": 1}]


def test_api_unknown_graduate_id_is_400(client, ctx):
    s = School(ctx.admin, ctx.catalog)
    resp = client.post(
        f"{BASE}/preview/",
        {"schools": [{"school_id": s.pid, "graduate_child_ids": [999999999]}]},
        content_type="application/json",
        **auth_headers(ctx.admin),
    )
    assert resp.status_code == 400


def test_api_too_many_schools_is_422(client, ctx):
    resp = client.post(
        f"{BASE}/precheck/",
        {"school_ids": list(range(1, 102))},
        content_type="application/json",
        **auth_headers(ctx.admin),
    )
    assert resp.status_code == 422


def test_api_preview_children_paginated_without_personal_data(client, ctx):
    s = School(ctx.admin, ctx.catalog)
    g = s.section()
    for i in range(3):
        s.child("8", g, first=f"Eight{i}")
    s.child("5", g, first="Five")

    body = client.get(
        f"{BASE}/preview/{s.pid}/children/?class_id={ctx.catalog['8'].pk}&page_size=2",
        **auth_headers(ctx.admin),
    ).json()

    assert body["total"] == 3
    assert len(body["results"]) == 2
    assert set(body["results"][0]) == {
        "child_id",
        "first_name",
        "last_name",
        "class_id",
        "class_name",
        "section_name",
    }


@pytest.mark.parametrize("role", ["CO Full Time", "CHO", "CXO"])
def test_api_non_admin_forbidden(client, ctx, role):
    user = make_user(role)
    assert client.get(f"{BASE}/eligible-schools/", **auth_headers(user)).status_code == 403
    resp = client.post(
        f"{BASE}/precheck/",
        {"school_ids": [1]},
        content_type="application/json",
        **auth_headers(user),
    )
    assert resp.status_code == 403
