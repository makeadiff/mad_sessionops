"""Slots and volunteer assignments count only in the school's own ACTIVE school-year
— on every screen, in R6, and in every export (M9 decision 9, reinterpreted by
M10 F-M10-3: the school's own year, not the global flag).

Each test seeds one active-year slot-class and one slot-class on an ARCHIVED
(2025-2026) school-year at the same school, both staffed by the same volunteer,
and checks the archived one is invisible everywhere.
"""

from datetime import time

import pytest

from sessionops.exceptions import ConflictError
from sessionops.models import (
    AcademicYear,
    SchoolAcademicYear,
    Slot,
    SlotClassSectionVolunteer,
    User,
)
from sessionops.services.academic_year.queries import current_year_q
from sessionops.services.exports.gaps import GAPS_HEADER, gap_rows
from sessionops.services.exports.schools import SCHOOLS_HEADER, schools_summary_rows
from sessionops.services.exports.timetable import TIMETABLE_HEADER, school_timetable_rows
from sessionops.services.exports.volunteers import VOLUNTEERS_HEADER, school_volunteer_rows
from sessionops.services.schools.queries import get_school_stats
from sessionops.services.slot_classes.helpers import check_r6_volunteer_single_assignment
from sessionops.services.slot_classes.schedule import get_school_schedule
from sessionops.services.slots.create import list_slots
from sessionops.services.volunteers.list import list_school_volunteers
from sessionops.tests.exports.factories import (
    active_year,
    assign,
    make_bucket,
    make_school,
    make_slot,
    make_slot_class,
    make_user,
)


@pytest.fixture
def setup(db):
    admin = make_user("Function Lead")
    year = active_year(admin)
    partner, wid = make_school(name="Mixed Years")
    pid = partner.partner_id
    vol = make_user("Wingman", wid, name="Asha")

    current = make_slot(pid, admin, "monday", time(10, 0), time(11, 0))
    assign(make_slot_class(current, make_bucket(pid, admin, "Current"), admin), vol, admin)

    old_year = AcademicYear.objects.create(label="2025-2026", is_active=False, created_by=admin)
    # Archived old school-year (F-M10-2: a school has exactly one active school-year).
    old_say = SchoolAcademicYear.objects.create(
        school_id=pid, academic_year_id=old_year, is_active=False, created_by=admin
    )
    old = Slot.objects.create(
        school_id=pid,
        school_academic_year_id=old_say,
        slot_name="Old Friday",
        day_of_week="friday",
        start_time=time(9, 0),
        end_time=time(10, 0),
        created_by=admin,
    )
    old_scs = make_slot_class(old, make_bucket(pid, admin, "Old"), admin)
    assign(old_scs, vol, admin)
    return {"admin": admin, "year": year, "pid": pid, "current": current, "old": old}


def _col(header, name):
    return header.index(name)


# ── Screens ────────────────────────────────────────────────────────────────────


def test_slots_tab_lists_only_active_year(setup):
    assert [s.slot_id for s in list_slots(setup["pid"], setup["admin"])] == [
        setup["current"].slot_id
    ]


def test_volunteers_tab_counts_only_active_year(setup):
    vols = list_school_volunteers(setup["pid"], setup["admin"])["volunteers"]
    assert [v["active_slot_class_count"] for v in vols] == [1]


def test_school_list_assignment_count_only_active_year(setup):
    assert get_school_stats([setup["pid"]])[setup["pid"]]["assignments_count"] == 1


def test_schedule_only_active_year(setup):
    schedule = get_school_schedule(setup["pid"], setup["admin"])
    slot_ids = [s["slot_id"] for d in schedule["days"] for s in d["slots"]]
    assert slot_ids == [setup["current"].slot_id]


# ── Exports ────────────────────────────────────────────────────────────────────


def test_volunteer_export_only_active_year(setup):
    (row,) = school_volunteer_rows(setup["pid"])
    assert row[_col(VOLUNTEERS_HEADER, "slot_class_count")] == 1
    assert "Friday" not in row[_col(VOLUNTEERS_HEADER, "assignments")]


def test_timetable_export_only_active_year(setup):
    rows = school_timetable_rows(setup["pid"])
    assert [r[_col(TIMETABLE_HEADER, "day")] for r in rows] == ["Monday"]


def test_schools_summary_counts_only_active_year(setup):
    (row,) = schools_summary_rows([setup["pid"]])
    assert row[_col(SCHOOLS_HEADER, "slots")] == 1
    assert row[_col(SCHOOLS_HEADER, "slot_classes")] == 1


def test_gap_report_ignores_old_year_slots(setup):
    # Retire the current slot: the school now has only an old-year slot → SCHOOL_NO_SLOTS,
    # and the old unstaffed-or-not slot-class never appears as a gap.
    Slot.objects.filter(pk=setup["current"].pk).update(is_active=False, removed=True)

    types = [r[_col(GAPS_HEADER, "gap_type")] for r in gap_rows([setup["pid"]])]

    assert "SCHOOL_NO_SLOTS" in types
    assert "SLOT_CLASS_NO_VOLUNTEER" not in types
    assert "VOLUNTEER_UNASSIGNED" in types  # old-year assignment doesn't count


def test_school_on_older_year_sees_its_own_data(setup):
    """A school not yet progressed (its active school-year is 2025-26) sees 2025-26 data,
    whatever the global year is (F-M10-3)."""
    old_say = setup["old"].school_academic_year_id
    current_say = setup["current"].school_academic_year_id
    SchoolAcademicYear.objects.filter(pk=current_say.pk).update(is_active=False)
    SchoolAcademicYear.objects.filter(pk=old_say.pk).update(is_active=True)

    assert [s.slot_id for s in list_slots(setup["pid"], setup["admin"])] == [setup["old"].slot_id]


def test_global_year_flag_does_not_scope_reads(setup):
    AcademicYear.objects.update(is_active=False)

    assert [s.slot_id for s in list_slots(setup["pid"], setup["admin"])] == [
        setup["current"].slot_id
    ]


def test_school_with_no_active_school_year_sees_nothing(setup):
    SchoolAcademicYear.objects.filter(school_id=setup["pid"]).update(is_active=False)

    assert not Slot.objects.filter(current_year_q(), school_id=setup["pid"]).exists()
    assert list_slots(setup["pid"], setup["admin"]) == []


# ── R6 (one active slot-class per volunteer) counts the active year only ───────


def test_r6_blocks_on_current_year_assignment(setup):
    vol = User.objects.get(user_display_name="Asha")
    with pytest.raises(ConflictError):
        check_r6_volunteer_single_assignment(vol)


def test_r6_ignores_old_year_assignment(setup):
    vol = User.objects.get(user_display_name="Asha")
    # Leave only the old-year assignment: she shows as unassigned, so she must be assignable.
    SlotClassSectionVolunteer.objects.filter(
        volunteer_id=vol, slot_class_section_id__slot_id=setup["current"]
    ).update(is_active=False, removed=True)

    check_r6_volunteer_single_assignment(vol)  # no ConflictError
    assert (
        list_school_volunteers(setup["pid"], setup["admin"])["volunteers"][0][
            "active_slot_class_count"
        ]
        == 0
    )
