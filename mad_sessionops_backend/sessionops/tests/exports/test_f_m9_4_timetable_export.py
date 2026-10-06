"""F-M9-4: School timetable export — service + API."""

from datetime import time

from django.test import Client

import pytest

from sessionops.models import (
    AcademicYear,
    ExportLog,
    Slot,
    SlotClassSection,
    SlotClassSectionVolunteer,
)
from sessionops.services.exports.timetable import TIMETABLE_HEADER, school_timetable_rows
from sessionops.services.slot_classes.schedule import get_school_schedule
from sessionops.tests.exports.factories import (
    assign,
    auth_headers,
    make_bucket,
    make_school,
    make_slot,
    make_slot_class,
    make_user,
    parse_csv,
    place_child,
)

COL = {name: i for i, name in enumerate(TIMETABLE_HEADER)}


@pytest.fixture
def setup(db):
    """Tue 10:00 slot (6th Group B Maths + 5th Group A English) and Mon 14:00 slot (5th Group A English)."""
    admin = make_user()
    partner, wid = make_school()
    pid = partner.partner_id
    group_a = make_bucket(pid, admin, "Group A", class_code="5")
    group_b = make_bucket(pid, admin, "Group B", class_code="6")
    tue = make_slot(pid, admin, "tuesday", time(10, 0), time(11, 0))
    mon = make_slot(pid, admin, "monday", time(14, 0), time(15, 0))
    tue_b = make_slot_class(tue, group_b, admin, "Maths")
    tue_a = make_slot_class(tue, group_a, admin, "English")
    mon_a = make_slot_class(mon, group_a, admin, "English")
    zara = make_user("Wingman", wid, name="Zara")
    amit = make_user("Wingman", wid, name="Amit")
    assign(tue_a, zara, admin)
    assign(tue_a, amit, admin)
    for name in ("Anu", "Bala", "Chitra"):
        place_child(group_a, admin, name)
    return {
        "admin": admin,
        "partner": partner,
        "tue": tue,
        "mon": mon,
        "tue_a": tue_a,
        "tue_b": tue_b,
        "mon_a": mon_a,
        "group_a": group_a,
    }


def _rows(setup):
    return school_timetable_rows(setup["partner"].partner_id)


# ── Service ────────────────────────────────────────────────────────────────────


def test_one_row_per_slot_class_ordered_by_day_time_class(setup):
    rows = _rows(setup)

    assert [(r[COL["day"]], r[COL["class"]], r[COL["subject"]]) for r in rows] == [
        ("Monday", "5th", "English"),
        ("Tuesday", "5th", "English"),
        ("Tuesday", "6th", "Maths"),
    ]
    assert rows[0][COL["start_time"]] == time(14, 0)
    assert rows[0][COL["end_time"]] == time(15, 0)


def test_volunteers_joined_sorted_and_counted(setup):
    tue_a = _rows(setup)[1]

    assert tue_a[COL["volunteers"]] == "Amit; Zara"
    assert tue_a[COL["volunteer_count"]] == 2


def test_soft_deleted_assignment_not_counted(setup):
    SlotClassSectionVolunteer.objects.filter(
        slot_class_section_id=setup["tue_a"], volunteer_id__user_display_name="Zara"
    ).update(is_active=False, removed=True)

    tue_a = _rows(setup)[1]

    assert (tue_a[COL["volunteers"]], tue_a[COL["volunteer_count"]]) == ("Amit", 1)


def test_children_in_bucket_counts_active_placements(setup):
    place_child(setup["group_a"], setup["admin"], "Moved", placement_active=False)

    rows = _rows(setup)

    assert rows[0][COL["children_in_bucket"]] == 3  # Group A
    assert rows[2][COL["children_in_bucket"]] == 0  # Group B, no children


def test_empty_slot_gets_one_blank_row(setup):
    make_slot(setup["partner"].partner_id, setup["admin"], "saturday", time(9, 0), time(10, 0))

    empty = _rows(setup)[-1]

    assert empty[COL["day"]] == "Saturday"
    assert (empty[COL["class"]], empty[COL["bucket"]], empty[COL["subject"]]) == (
        None,
        None,
        None,
    )
    assert (empty[COL["volunteers"]], empty[COL["volunteer_count"]]) == ("", 0)


def test_classless_bucket_has_blank_class(setup):
    pid = setup["partner"].partner_id
    bucket = make_bucket(pid, setup["admin"], "Circle 1", class_code=None)
    make_slot_class(
        make_slot(pid, setup["admin"], "friday"),
        bucket,
        setup["admin"],
        "Foundation Day 1",
    )

    friday = _rows(setup)[-1]

    assert friday[COL["class"]] is None
    assert friday[COL["bucket"]] == "Circle 1"
    assert friday[COL["subject"]] == "Foundation"  # normalised like the Slots tab


def test_inactive_slot_and_slot_class_excluded(setup):
    Slot.objects.filter(pk=setup["mon"].pk).update(is_active=False, removed=True)
    SlotClassSection.objects.filter(pk=setup["tue_b"].pk).update(is_active=False, removed=True)

    rows = _rows(setup)

    assert [(r[COL["day"]], r[COL["subject"]]) for r in rows] == [("Tuesday", "English")]


def test_matches_schedule_service(setup):
    schedule = get_school_schedule(setup["partner"].partner_id, setup["admin"])
    expected = sorted(
        (
            sc["slot_class_section_id"],
            len(sc["volunteers"]),
            sc["active_children_count"],
        )
        for day in schedule["days"]
        for slot in day["slots"]
        for sc in slot["slot_classes"]
    )
    by_scs = {
        setup["tue_a"].pk: (2, 3),
        setup["tue_b"].pk: (0, 0),
        setup["mon_a"].pk: (0, 3),
    }

    assert expected == sorted((pk, *vals) for pk, vals in by_scs.items())
    rows = _rows(setup)
    assert sorted(
        (r[COL["volunteer_count"]], r[COL["children_in_bucket"]]) for r in rows
    ) == sorted(by_scs.values())


def test_no_slots_returns_empty(db):
    partner, _ = make_school()
    assert school_timetable_rows(partner.partner_id) == []


def test_query_count_is_constant(setup, django_assert_max_num_queries):
    pid = setup["partner"].partner_id
    for day in ("wednesday", "thursday", "friday"):
        slot = make_slot(pid, setup["admin"], day)
        make_slot_class(slot, make_bucket(pid, setup["admin"], f"G {day}"), setup["admin"])

    with django_assert_max_num_queries(4):
        rows = school_timetable_rows(pid)

    assert len(rows) == 6


def test_row_width_matches_header(setup):
    for row in _rows(setup):
        assert len(row) == len(TIMETABLE_HEADER)


# ── API ────────────────────────────────────────────────────────────────────────


def _url(school_id: int) -> str:
    return f"/api/schools/{school_id}/exports/timetable.csv"


@pytest.fixture
def client():
    return Client()


def test_api_returns_csv_and_logs(client, setup):
    pid = setup["partner"].partner_id

    response = client.get(_url(pid), **auth_headers(setup["admin"]))

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith(f'attachment; filename="timetable_{pid}_')
    table = parse_csv(response)
    assert table[0] == TIMETABLE_HEADER
    assert table[1][:4] == ["Monday", "Monday 14:00", "14:00", "15:00"]
    assert len(table) == 1 + 3
    log = ExportLog.objects.get()
    assert (log.export_type, log.school_id, log.row_count) == (
        "school_timetable",
        pid,
        3,
    )


def test_api_co_cannot_export_other_school(client, setup):
    response = client.get(
        _url(setup["partner"].partner_id), **auth_headers(make_user("CO Full Time"))
    )

    assert response.status_code == 403
    assert ExportLog.objects.count() == 0


def test_api_unknown_school_is_404(client, setup):
    assert client.get(_url(999_999_999), **auth_headers(setup["admin"])).status_code == 404


def test_api_no_active_year_is_404(client, setup):
    AcademicYear.objects.update(is_active=False)

    response = client.get(_url(setup["partner"].partner_id), **auth_headers(setup["admin"]))

    assert response.status_code == 404
    assert ExportLog.objects.count() == 0


def test_api_requires_auth(client, setup):
    assert client.get(_url(setup["partner"].partner_id)).status_code == 401
