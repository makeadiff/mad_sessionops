"""F-M10-3: reads are scoped to the school's own active school-year.

Fixture: one school with an ARCHIVED 2025-26 school-year (a class, a bucket, a slot,
a session) and an ACTIVE 2026-27 school-year with its own set. Every surface must
show only the active year. A second school still on 2025-26 (active) must keep
seeing its own 2025-26 data.
"""

from datetime import date, time

from django.db.models import Q

import pytest

from sessionops.exceptions import ConflictError
from sessionops.models import (
    AcademicYear,
    ClassSection,
    SchoolAcademicYear,
    SchoolClass,
    SchoolSessionDetails,
    Slot,
)
from sessionops.services.academic_year.queries import current_year_q
from sessionops.services.exports.schools import SCHOOLS_HEADER, schools_summary_rows
from sessionops.services.holidays.create import create_holiday
from sessionops.services.schools.queries import get_school_stats
from sessionops.services.sections.slug import normalize_section_slug
from sessionops.services.sessions.get_defaults import get_session_defaults
from sessionops.services.sessions.queries import get_active_session
from sessionops.services.slots.create import create_slot, list_slots
from sessionops.services.structure.queries import list_classes_for_school
from sessionops.services.structure.sections import (
    create_bucket,
    list_buckets_for_school,
    list_sections_for_class,
)
from sessionops.tests.exports.factories import (
    active_year,
    make_bucket,
    make_school,
    make_school_class,
    make_slot,
    make_user,
    school_year,
)

COL = {n: i for i, n in enumerate(SCHOOLS_HEADER)}


def _old_year(admin):
    year, _ = AcademicYear.objects.get_or_create(
        label="2025-2026", defaults={"is_active": False, "created_by": admin}
    )
    return year


def _session(say, admin, start, end):
    return SchoolSessionDetails.objects.create(
        school_id=say.school_id,
        school_academic_year=say,
        start_date=start,
        end_date=end,
        created_by=admin,
    )


@pytest.fixture
def setup(db):
    admin = make_user("Function Lead")
    active_year(admin)
    partner, _ = make_school(name="Progressed")
    pid = partner.partner_id

    # Archived 2025-26 data (what progression leaves behind).
    old_say = SchoolAcademicYear.objects.create(
        school_id=pid,
        academic_year_id=_old_year(admin),
        is_active=False,
        created_by=admin,
    )
    old_class = SchoolClass.objects.create(
        school_id=pid,
        school_academic_year_id=old_say,
        class_id=make_school_class(pid, admin, "5").class_id,
        created_by=admin,
    )
    old_bucket = make_bucket(pid, admin, "Group A", class_code=None)
    ClassSection.objects.filter(pk=old_bucket.pk).update(
        school_academic_year_id=old_say,
        is_active=False,
        section_name=normalize_section_slug("Group A"),  # real slug, so name reuse is tested
    )
    old_slot = Slot.objects.create(
        school_id=pid,
        school_academic_year_id=old_say,
        slot_name="Old Monday",
        day_of_week="monday",
        start_time=time(10, 0),
        end_time=time(11, 0),
        created_by=admin,
    )
    _session(old_say, admin, date(2025, 7, 1), date(2026, 3, 31))

    # Active 2026-27 data.
    new_say = school_year(pid, admin)
    new_class = SchoolClass.objects.get(school_id=pid, school_academic_year_id=new_say)
    new_bucket = make_bucket(pid, admin, "Group B", class_code=None)
    new_slot = make_slot(pid, admin, "tuesday", time(10, 0), time(11, 0))
    _session(new_say, admin, date(2026, 7, 1), date(2027, 3, 31))

    return {
        "admin": admin,
        "pid": pid,
        "old_say": old_say,
        "old_class": old_class,
        "old_slot": old_slot,
        "new_say": new_say,
        "new_class": new_class,
        "new_bucket": new_bucket,
        "new_slot": new_slot,
    }


# ── Structure ──────────────────────────────────────────────────────────────────


def test_class_list_only_active_year(setup):
    assert [sc.pk for sc in list_classes_for_school(setup["pid"])] == [setup["new_class"].pk]


def test_bucket_list_only_active_year(setup):
    names = [b.section_display_name for b in list_buckets_for_school(setup["pid"])]
    assert names == ["Group B"]


def test_archived_bucket_name_can_be_reused(setup):
    bucket = create_bucket(setup["pid"], "Group A", setup["admin"])
    assert bucket.school_academic_year_id == setup["new_say"]


def test_active_bucket_name_still_conflicts(setup):
    create_bucket(setup["pid"], "Group C", setup["admin"])
    with pytest.raises(ConflictError):
        create_bucket(setup["pid"], "Group C", setup["admin"])


def test_legacy_section_without_school_year_stays_visible(setup):
    legacy = make_bucket(setup["pid"], setup["admin"], "Legacy", class_code=None)
    ClassSection.objects.filter(pk=legacy.pk).update(school_academic_year_id=None)

    names = {b.section_display_name for b in list_buckets_for_school(setup["pid"])}

    assert names == {"Group B", "Legacy"}


def test_sections_for_class_scoped(setup):
    section = make_bucket(setup["pid"], setup["admin"], "5th A", class_code="5")
    assert [s.pk for s in list_sections_for_class(section.school_class_id_id)] == [section.pk]


# ── Slots / R7 ─────────────────────────────────────────────────────────────────


def test_slot_list_only_active_year(setup):
    assert [s.pk for s in list_slots(setup["pid"], setup["admin"])] == [setup["new_slot"].pk]


def test_archived_slot_does_not_cause_overlap(setup):
    # Old slot: Monday 10–11 on the archived year. Same time in the new year is fine.
    slot = create_slot(setup["pid"], "monday", time(10, 0), time(11, 0), setup["admin"])
    assert slot.school_academic_year_id == setup["new_say"]


def test_active_year_overlap_still_rejected(setup):
    with pytest.raises(ConflictError):
        create_slot(setup["pid"], "tuesday", time(10, 30), time(11, 30), setup["admin"])


# ── Session / holidays ─────────────────────────────────────────────────────────


def test_active_session_is_the_school_years(setup):
    assert get_active_session(setup["pid"]).start_date == date(2026, 7, 1)


def test_holiday_window_uses_school_years_session(setup):
    # Inside the 2026-27 session: allowed.
    create_holiday(
        setup["pid"],
        {
            "holiday_reason": "holidays",
            "start_date": date(2026, 10, 1),
            "end_date": date(2026, 10, 2),
        },
        setup["admin"],
    )
    # Inside only the archived 2025-26 session: rejected.
    from sessionops.exceptions import ValidationError

    with pytest.raises(ValidationError):
        create_holiday(
            setup["pid"],
            {
                "holiday_reason": "holidays",
                "start_date": date(2025, 10, 1),
                "end_date": date(2025, 10, 2),
            },
            setup["admin"],
        )


def test_session_defaults_label_is_school_years(setup, db):
    partner, _ = make_school(name="On old year")
    SchoolAcademicYear.objects.create(
        school_id=partner.partner_id,
        academic_year_id=_old_year(setup["admin"]),
        created_by=setup["admin"],
    )
    assert (
        get_session_defaults(partner.partner_id, setup["admin"])["academic_year_label"]
        == "2025-2026"
    )
    assert get_session_defaults(setup["pid"], setup["admin"])["academic_year_label"] == "2026-2027"


# ── Counts / exports, and a school still on the older year ─────────────────────


def test_school_stats_classes_only_active_year(setup):
    assert get_school_stats([setup["pid"]])[setup["pid"]]["classes_count"] == 1


def test_two_schools_each_see_their_own_year(setup):
    admin = setup["admin"]
    behind, _ = make_school(name="Still on 2025-26")
    bid = behind.partner_id
    say = SchoolAcademicYear.objects.create(
        school_id=bid, academic_year_id=_old_year(admin), created_by=admin
    )
    Slot.objects.create(
        school_id=bid,
        school_academic_year_id=say,
        slot_name="Behind Monday",
        day_of_week="monday",
        start_time=time(9, 0),
        end_time=time(10, 0),
        created_by=admin,
    )
    _session(say, admin, date(2025, 7, 1), date(2026, 3, 31))

    rows = {r[COL["partner_id"]]: r for r in schools_summary_rows([setup["pid"], bid])}

    assert rows[setup["pid"]][COL["slots"]] == 1
    assert rows[setup["pid"]][COL["term_start"]] == date(2026, 7, 1)
    assert rows[bid][COL["slots"]] == 1
    assert rows[bid][COL["term_start"]] == date(2025, 7, 1)
    assert [s.slot_name for s in list_slots(bid, admin)] == ["Behind Monday"]


def test_current_year_q_ignores_global_flag(setup):
    AcademicYear.objects.update(is_active=False)
    assert set(Slot.objects.filter(current_year_q()).values_list("pk", flat=True)) == {
        setup["new_slot"].pk
    }
    assert not Slot.objects.filter(current_year_q(), ~Q(pk=setup["new_slot"].pk)).exists()
