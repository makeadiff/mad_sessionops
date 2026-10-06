"""F-M9-8: Ops gap report — service + API."""

from datetime import date, time

from django.test import Client

import pytest

from sessionops.models import (
    AcademicYear,
    Child,
    ExportLog,
    Partner,
    SchoolSessionDetails,
    Slot,
    SlotClassSectionVolunteer,
)
from sessionops.services.children.queries import list_children
from sessionops.services.exports.gaps import GAP_TYPES, GAPS_HEADER, gap_rows
from sessionops.services.volunteers.list import list_school_volunteers
from sessionops.tests.exports.factories import (
    active_year,
    assign,
    auth_headers,
    make_bucket,
    make_school,
    make_slot,
    make_slot_class,
    make_user,
    parse_csv,
    place_child,
    school_year,
)

COL = {name: i for i, name in enumerate(GAPS_HEADER)}


def _set_term(school_id, admin, say=None):
    return SchoolSessionDetails.objects.create(
        school_id=school_id,
        school_academic_year=say or school_year(school_id, admin),
        start_date=date(2026, 7, 1),
        end_date=date(2027, 3, 31),
        created_by=admin,
    )


def _complete_school(admin, name="Complete School"):
    """Fully set up: term dates, a slot, every child bucketed, slot-class staffed, volunteer assigned."""
    partner, wid = make_school(name=name, city="Pune", co_name="Meera")
    pid = partner.partner_id
    _set_term(pid, admin)
    bucket = make_bucket(pid, admin, "Group A")
    place_child(bucket, admin, "Anu")
    scs = make_slot_class(make_slot(pid, admin, "monday", time(10, 0), time(11, 0)), bucket, admin)
    assign(scs, make_user("Wingman", wid, name="Vol"), admin)
    return partner, wid, bucket, scs


@pytest.fixture
def admin(db):
    user = make_user("Function Lead")
    active_year(user)
    return user


@pytest.fixture
def gappy(admin):
    """One school with exactly one gap of each type."""
    partner, wid = make_school(name="Gappy School", city="Delhi", co_name="Ravi")
    pid = partner.partner_id
    # No term dates, no slots → both school-level gaps.
    bucket = make_bucket(pid, admin, "Group A")
    place_child(bucket, admin, "Placed")
    Child.objects.create(
        school_id=pid,
        first_name="Nisha",
        last_name="Rao",
        gender="female",
        age=9,
        created_by=admin,
    )
    make_user("Wingman", wid, name="Idle Vol", contact="9999900000")
    return partner


def _types(rows):
    return [r[COL["gap_type"]] for r in rows]


# ── Each gap type ──────────────────────────────────────────────────────────────


def test_complete_school_has_no_gaps(admin):
    partner, *_ = _complete_school(admin)
    assert gap_rows([partner.partner_id]) == []


def test_school_no_term_dates(admin):
    partner, *_ = _complete_school(admin)
    SchoolSessionDetails.objects.filter(school_id=partner.partner_id).update(is_active=False)

    rows = gap_rows([partner.partner_id])

    assert _types(rows) == ["SCHOOL_NO_TERM_DATES"]
    assert rows[0][COL["detail"]] == "No term dates set for 2026-2027"
    assert rows[0][COL["entity_id"]] is None


def test_term_dates_for_other_year_still_a_gap(admin):
    partner, *_ = _complete_school(admin)
    pid = partner.partner_id
    SchoolSessionDetails.objects.filter(school_id=pid).delete()
    old = AcademicYear.objects.create(label="2025-2026", is_active=False, created_by=admin)
    say_old = school_year(pid, admin)
    say_old.pk = None
    say_old.academic_year_id = old
    say_old.is_active = False  # archived old year (F-M10-2: one active school-year per school)
    say_old.save()
    _set_term(pid, admin, say=say_old)

    assert _types(gap_rows([pid])) == ["SCHOOL_NO_TERM_DATES"]


def test_school_no_slots(admin):
    partner, *_ = _complete_school(admin)
    Slot.objects.filter(school_id=partner.partner_id).update(is_active=False, removed=True)

    types = _types(gap_rows([partner.partner_id]))

    # Deleting the only slot also leaves the volunteer unassigned.
    assert types == ["SCHOOL_NO_SLOTS", "VOLUNTEER_UNASSIGNED"]


def test_child_no_bucket(admin):
    partner, _, bucket, _ = _complete_school(admin)
    Child.objects.create(
        school_id=partner.partner_id,
        first_name="Nisha",
        last_name="Rao",
        gender="female",
        age=9,
        created_by=admin,
    )
    place_child(bucket, admin, "Moved", placement_active=False)  # placement retired → unplaced

    rows = gap_rows([partner.partner_id])

    assert _types(rows) == ["CHILD_NO_BUCKET", "CHILD_NO_BUCKET"]
    assert [r[COL["entity_name"]] for r in rows] == ["Moved Kumar", "Nisha Rao"]


def test_inactive_unplaced_child_is_not_a_gap(admin):
    partner, *_ = _complete_school(admin)
    Child.objects.create(
        school_id=partner.partner_id,
        first_name="Gone",
        last_name="X",
        gender="male",
        age=9,
        is_active=False,
        created_by=admin,
    )
    assert gap_rows([partner.partner_id]) == []


def test_slot_class_no_volunteer(admin):
    partner, _, bucket, scs = _complete_school(admin)
    SlotClassSectionVolunteer.objects.filter(slot_class_section_id=scs).update(
        is_active=False, removed=True
    )

    rows = gap_rows([partner.partner_id])

    assert _types(rows) == ["SLOT_CLASS_NO_VOLUNTEER", "VOLUNTEER_UNASSIGNED"]
    gap = rows[0]
    assert gap[COL["entity_id"]] == scs.slot_class_section_id
    assert gap[COL["entity_name"]] == "Monday 10:00-11:00 · 5th · Group A · English"
    assert gap[COL["detail"]] == "1 child in bucket"


def test_slot_class_on_inactive_slot_is_not_a_gap(admin):
    partner, _, bucket, _ = _complete_school(admin)
    dead = make_slot(partner.partner_id, admin, "friday", is_active=False, removed=True)
    make_slot_class(dead, bucket, admin)

    assert gap_rows([partner.partner_id]) == []


def test_volunteer_unassigned(admin):
    partner, wid, *_ = _complete_school(admin)
    make_user("Wingman", wid, name="Idle", contact="9999900000")

    rows = gap_rows([partner.partner_id])

    assert _types(rows) == ["VOLUNTEER_UNASSIGNED"]
    assert (rows[0][COL["entity_name"]], rows[0][COL["detail"]]) == (
        "Idle",
        "9999900000",
    )


# ── All types together, ordering, parity with the tabs ─────────────────────────


def test_all_five_types_across_two_schools(admin, gappy):
    """One school can't have both SCHOOL_NO_SLOTS and SLOT_CLASS_NO_VOLUNTEER (the second
    needs a slot), so the five types are seeded across gappy (no slots) and a second
    school with an unstaffed slot-class."""
    staffed, *_ = _complete_school(admin, "Zeta School")
    make_slot_class(
        make_slot(staffed.partner_id, admin, "tuesday"),
        make_bucket(staffed.partner_id, admin, "Group B"),
        admin,
    )
    ids = [gappy.partner_id, staffed.partner_id]

    rows = gap_rows(ids)

    assert set(_types(rows)) == set(GAP_TYPES)
    assert [(r[COL["school_name"]], r[COL["gap_type"]]) for r in rows] == [
        ("Gappy School", "SCHOOL_NO_TERM_DATES"),
        ("Gappy School", "SCHOOL_NO_SLOTS"),
        ("Gappy School", "CHILD_NO_BUCKET"),
        ("Gappy School", "VOLUNTEER_UNASSIGNED"),
        ("Zeta School", "SLOT_CLASS_NO_VOLUNTEER"),
    ]


def test_gap_types_follow_defined_order(admin, gappy):
    types = _types(gap_rows([gappy.partner_id]))
    assert [t for t in GAP_TYPES if t in types] == types


def test_rows_follow_given_school_order(admin, gappy):
    complete, *_ = _complete_school(admin, "Complete")
    bare, _ = make_school(name="Bare")
    ids = [bare.partner_id, gappy.partner_id, complete.partner_id]

    names = [r[COL["school_name"]] for r in gap_rows(ids)]

    first_seen = list(dict.fromkeys(names))
    assert first_seen == ["Bare", "Gappy School"]  # given order; Complete has no gaps


def test_child_gaps_match_children_tab_unassigned(admin, gappy):
    rows = gap_rows([gappy.partner_id])
    from_report = {r[COL["entity_id"]] for r in rows if r[COL["gap_type"]] == "CHILD_NO_BUCKET"}
    from_tab = {
        c.child_id for c in list_children(gappy.partner_id, status="active", unassigned=True)
    }
    assert from_report == from_tab


def test_volunteer_gaps_match_volunteers_tab(admin, gappy):
    rows = gap_rows([gappy.partner_id])
    from_report = {
        r[COL["entity_id"]] for r in rows if r[COL["gap_type"]] == "VOLUNTEER_UNASSIGNED"
    }
    tab = list_school_volunteers(gappy.partner_id, admin)["volunteers"]
    assert from_report == {v["user_id"] for v in tab if v["active_slot_class_count"] == 0}


def test_school_columns(admin, gappy):
    row = gap_rows([gappy.partner_id])[0]
    assert row[:4] == [gappy.partner_id, "Gappy School", "Delhi", "Ravi"]


def test_empty_ids(admin):
    assert gap_rows([]) == []


def test_query_count_is_constant(admin, gappy, django_assert_max_num_queries):
    ids = [gappy.partner_id]
    with django_assert_max_num_queries(12) as baseline:
        gap_rows(ids)
    n = len(baseline.captured_queries)

    for i in range(4):
        ids.append(_complete_school(admin, f"Extra {i}")[0].partner_id)
        ids.append(make_school(name=f"Bare {i}")[0].partner_id)
    with django_assert_max_num_queries(n):
        gap_rows(ids)


# ── API ────────────────────────────────────────────────────────────────────────

URL = "/api/exports/gaps.csv"


@pytest.fixture
def client():
    return Client()


def test_api_returns_csv_and_logs(client, admin, gappy):
    response = client.get(URL, **auth_headers(admin))

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith('attachment; filename="gaps_all_')
    table = parse_csv(response)
    assert table[0] == GAPS_HEADER
    assert [r[COL["gap_type"]] for r in table[1:]] == [
        "SCHOOL_NO_TERM_DATES",
        "SCHOOL_NO_SLOTS",
        "CHILD_NO_BUCKET",
        "VOLUNTEER_UNASSIGNED",
    ]
    log = ExportLog.objects.get()
    assert (log.export_type, log.school_id, log.school_count, log.row_count) == (
        "gap_report",
        None,
        1,
        4,
    )


def test_api_search_narrows_and_is_logged(client, admin, gappy):
    _complete_school(admin, "Complete")
    make_school(name="Other Gappy", co_name="Someone")

    response = client.get(URL, {"search": "ravi"}, **auth_headers(admin))

    assert {r[COL["school_name"]] for r in parse_csv(response)[1:]} == {"Gappy School"}
    assert ExportLog.objects.get().filters == {"search": "ravi"}


def test_api_co_gets_only_own_schools(client, admin, gappy):
    co = make_user("CO Full Time")
    other, _ = make_school(name="Mine")
    Partner.objects.filter(pk=other.pk).update(co_id=co.user_id)

    rows = parse_csv(client.get(URL, **auth_headers(co)))[1:]

    assert {r[COL["school_name"]] for r in rows} == {"Mine"}


def test_api_no_active_year_is_404(client, admin, gappy):
    AcademicYear.objects.update(is_active=False)

    assert client.get(URL, **auth_headers(admin)).status_code == 404
    assert ExportLog.objects.count() == 0


def test_api_requires_auth(client, admin):
    assert client.get(URL).status_code == 401
