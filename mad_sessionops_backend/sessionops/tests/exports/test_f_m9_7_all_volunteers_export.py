"""F-M9-7: All volunteers export (in scope) — service + API."""

from datetime import time

from django.test import Client

import pytest

from sessionops.models import AcademicYear, ExportLog, Partner, PartnerWorknode
from sessionops.services.exports.volunteers import (
    ALL_VOLUNTEERS_HEADER,
    VOLUNTEERS_HEADER,
    all_volunteer_rows,
    school_volunteer_rows,
)
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
)

COL = {name: i for i, name in enumerate(ALL_VOLUNTEERS_HEADER)}


@pytest.fixture
def setup(db):
    """Alpha (Delhi) and Bravo (Pune), each with its own worknode and volunteers.

    Asha is on Alpha's worknode, which Bravo also maps to (shared chapter);
    she teaches Monday at Alpha only.
    """
    admin = make_user("Function Lead")
    active_year(admin)
    alpha, wid_a = make_school(name="Alpha School", city="Delhi", co_name="Meera")
    bravo, wid_b = make_school(name="Bravo School", city="Pune", co_name="Ravi")
    PartnerWorknode.objects.create(partner_id=str(bravo.partner_id), worknode_id=wid_a)
    asha = make_user("Wingman", wid_a, name="Asha", city="Noida")
    make_user("Wingman", wid_b, name="Bilal")
    scs = make_slot_class(
        make_slot(alpha.partner_id, admin, "monday", time(10, 0), time(11, 0)),
        make_bucket(alpha.partner_id, admin, "Group A", class_code=None),
        admin,
    )
    assign(scs, asha, admin)
    return {"admin": admin, "alpha": alpha, "bravo": bravo}


def _ids(setup):
    return [setup["alpha"].partner_id, setup["bravo"].partner_id]  # name order


# ── Service ────────────────────────────────────────────────────────────────────


def test_rows_grouped_by_school_then_volunteer(setup):
    rows = all_volunteer_rows(_ids(setup))

    assert [(r[COL["school_name"]], r[COL["name"]]) for r in rows] == [
        ("Alpha School", "Asha"),
        ("Bravo School", "Asha"),  # shared worknode → listed under both
        ("Bravo School", "Bilal"),
    ]
    assert rows[0][COL["school_city"]] == "Delhi"
    assert rows[0][COL["city"]] == "Noida"  # volunteer's own city, distinct column


def test_shared_volunteer_lists_only_that_schools_assignments(setup):
    rows = {(r[COL["school_name"]], r[COL["name"]]): r for r in all_volunteer_rows(_ids(setup))}

    assert rows[("Alpha School", "Asha")][COL["slot_class_count"]] == 1
    assert rows[("Alpha School", "Asha")][COL["assignments"]].startswith("Monday 10:00-11:00")
    assert rows[("Bravo School", "Asha")][COL["slot_class_count"]] == 0
    assert rows[("Bravo School", "Asha")][COL["assignments"]] == ""


def test_each_school_matches_per_school_export(setup):
    rows = all_volunteer_rows(_ids(setup))

    for partner in (setup["alpha"], setup["bravo"]):
        mine = [r[3:] for r in rows if r[COL["school_id"]] == partner.partner_id]
        assert mine == school_volunteer_rows(partner.partner_id)


def test_only_given_schools_and_order_kept(setup):
    reversed_ids = list(reversed(_ids(setup)))
    names = [r[COL["school_name"]] for r in all_volunteer_rows(reversed_ids)]
    assert names == ["Bravo School", "Bravo School", "Alpha School"]
    assert {r[COL["school_name"]] for r in all_volunteer_rows([setup["alpha"].partner_id])} == {
        "Alpha School"
    }


def test_school_without_worknode_contributes_no_rows(setup):
    bare = Partner.objects.create(partner_id=12_345_678, partner_name="Bare", converted=True)
    rows = all_volunteer_rows([*_ids(setup), bare.partner_id])
    assert "Bare" not in {r[COL["school_name"]] for r in rows}


def test_empty_ids(setup):
    assert all_volunteer_rows([]) == []


def test_query_count_is_constant(setup, django_assert_max_num_queries):
    ids = _ids(setup)
    with django_assert_max_num_queries(10) as baseline:
        all_volunteer_rows(ids)
    n = len(baseline.captured_queries)

    for i in range(4):
        partner, wid = make_school(name=f"Extra {i}")
        make_user("Wingman", wid, name=f"V{i}")
        ids.append(partner.partner_id)
    with django_assert_max_num_queries(n):
        rows = all_volunteer_rows(ids)

    assert len(rows) == 3 + 4


def test_header_is_school_columns_plus_roster(setup):
    assert ALL_VOLUNTEERS_HEADER == [
        "school_id",
        "school_name",
        "school_city",
        *VOLUNTEERS_HEADER,
    ]
    assert len(set(ALL_VOLUNTEERS_HEADER)) == len(ALL_VOLUNTEERS_HEADER)


# ── API ────────────────────────────────────────────────────────────────────────

URL = "/api/exports/volunteers.csv"


@pytest.fixture
def client():
    return Client()


def test_api_admin_gets_all_schools(client, setup):
    response = client.get(URL, **auth_headers(setup["admin"]))

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith('attachment; filename="volunteers_all_')
    table = parse_csv(response)
    assert table[0] == ALL_VOLUNTEERS_HEADER
    assert len(table) == 1 + 3
    log = ExportLog.objects.get()
    assert (
        log.export_type,
        log.school_id,
        log.school_count,
        log.row_count,
        log.filters,
    ) == (
        "all_volunteers",
        None,
        2,
        3,
        {},
    )


def test_api_search_narrows_and_is_logged(client, setup):
    response = client.get(URL, {"search": "ravi"}, **auth_headers(setup["admin"]))  # Bravo's CO

    assert {r[COL["school_name"]] for r in parse_csv(response)[1:]} == {"Bravo School"}
    assert ExportLog.objects.get().filters == {"search": "ravi"}


def test_api_cho_gets_only_worknode_schools(client, setup):
    cho = make_user("CHO", worknode_id=515151)
    PartnerWorknode.objects.create(partner_id=str(setup["alpha"].partner_id), worknode_id=515151)

    rows = parse_csv(client.get(URL, **auth_headers(cho)))[1:]

    assert {r[COL["school_name"]] for r in rows} == {"Alpha School"}


def test_api_co_gets_only_own_schools(client, setup):
    co = make_user("CO Full Time")
    Partner.objects.filter(pk=setup["bravo"].pk).update(co_id=co.user_id)

    rows = parse_csv(client.get(URL, **auth_headers(co)))[1:]

    assert {r[COL["school_name"]] for r in rows} == {"Bravo School"}


def test_api_no_schools_is_header_only(client, setup):
    response = client.get(URL, **auth_headers(make_user("CHO", worknode_id=None)))
    assert parse_csv(response) == [ALL_VOLUNTEERS_HEADER]


def test_api_no_active_year_is_404(client, setup):
    AcademicYear.objects.update(is_active=False)

    assert client.get(URL, **auth_headers(setup["admin"])).status_code == 404
    assert ExportLog.objects.count() == 0


def test_api_requires_auth(client, setup):
    assert client.get(URL).status_code == 401
