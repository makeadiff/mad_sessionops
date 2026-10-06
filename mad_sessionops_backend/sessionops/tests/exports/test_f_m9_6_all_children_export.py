"""F-M9-6: All children export (in scope) — service + API."""

from django.test import Client

import pytest

from sessionops.models import AcademicYear, Child, ExportLog, Partner, PartnerWorknode
from sessionops.services.exports.children import (
    ALL_CHILDREN_HEADER,
    CHILDREN_HEADER,
    all_children_rows,
    school_children_rows,
)
from sessionops.tests.exports.factories import (
    active_year,
    auth_headers,
    make_bucket,
    make_school,
    make_user,
    parse_csv,
    place_child,
)

COL = {name: i for i, name in enumerate(ALL_CHILDREN_HEADER)}


@pytest.fixture
def setup(db):
    """Two schools (Bravo in Pune, Alpha in Delhi), 2 active + 1 inactive child each."""
    admin = make_user("Function Lead")
    active_year(admin)
    schools = {}
    for name, city in (("Bravo School", "Pune"), ("Alpha School", "Delhi")):
        partner, _ = make_school(name=name, city=city, co_name="Meera")
        bucket = make_bucket(partner.partner_id, admin, "Group A", class_code="5")
        place_child(bucket, admin, "Zoya")
        place_child(bucket, admin, "Anu")
        gone = place_child(bucket, admin, "Gone", placement_active=False)
        Child.objects.filter(pk=gone.pk).update(is_active=False)
        schools[name] = partner
    return {
        "admin": admin,
        "bravo": schools["Bravo School"],
        "alpha": schools["Alpha School"],
    }


def _ids(setup):
    # export_school_ids order: by name → Alpha, Bravo
    return [setup["alpha"].partner_id, setup["bravo"].partner_id]


# ── Service ────────────────────────────────────────────────────────────────────


def test_rows_grouped_by_school_in_given_order(setup):
    rows = all_children_rows(_ids(setup))

    assert [(r[COL["school_name"]], r[COL["first_name"]]) for r in rows] == [
        ("Alpha School", "Anu"),
        ("Alpha School", "Zoya"),
        ("Alpha School", "Gone"),  # no placement → sorts after placed children
        ("Bravo School", "Anu"),
        ("Bravo School", "Zoya"),
        ("Bravo School", "Gone"),
    ]
    assert rows[0][COL["school_city"]] == "Delhi"
    assert rows[0][COL["school_id"]] == setup["alpha"].partner_id


@pytest.mark.parametrize("status", ["all", "active", "inactive"])
def test_each_school_matches_per_school_export(setup, status):
    rows = all_children_rows(_ids(setup), status=status)

    for partner in (setup["alpha"], setup["bravo"]):
        mine = [r[3:] for r in rows if r[COL["school_id"]] == partner.partner_id]
        assert mine == school_children_rows(partner.partner_id, status=status)


def test_status_filters(setup):
    ids = _ids(setup)
    assert len(all_children_rows(ids, status="active")) == 4
    assert len(all_children_rows(ids, status="inactive")) == 2
    assert len(all_children_rows(ids)) == 6


def test_removed_children_never_exported(setup):
    Child.objects.filter(first_name="Zoya").update(removed=True)
    assert "Zoya" not in {r[COL["first_name"]] for r in all_children_rows(_ids(setup))}


def test_only_given_schools(setup):
    rows = all_children_rows([setup["bravo"].partner_id])
    assert {r[COL["school_name"]] for r in rows} == {"Bravo School"}


def test_empty_ids(setup):
    assert all_children_rows([]) == []


def test_query_count_is_constant(setup, django_assert_max_num_queries):
    ids = _ids(setup)
    with django_assert_max_num_queries(10) as baseline:
        all_children_rows(ids)
    n = len(baseline.captured_queries)

    for i in range(4):
        partner, _ = make_school(name=f"Extra {i}")
        place_child(make_bucket(partner.partner_id, setup["admin"]), setup["admin"], "Kid")
        ids.append(partner.partner_id)
    with django_assert_max_num_queries(n):
        rows = all_children_rows(ids)

    assert len(rows) == 10


def test_header_is_school_columns_plus_roster(setup):
    assert ALL_CHILDREN_HEADER == [
        "school_id",
        "school_name",
        "school_city",
        *CHILDREN_HEADER,
    ]
    assert len(set(ALL_CHILDREN_HEADER)) == len(ALL_CHILDREN_HEADER)  # no duplicate column names
    for row in all_children_rows(_ids(setup)):
        assert len(row) == len(ALL_CHILDREN_HEADER)


# ── API ────────────────────────────────────────────────────────────────────────

URL = "/api/exports/children.csv"


@pytest.fixture
def client():
    return Client()


def test_api_admin_gets_all_schools(client, setup):
    response = client.get(URL, **auth_headers(setup["admin"]))

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith('attachment; filename="children_all_')
    table = parse_csv(response)
    assert table[0] == ALL_CHILDREN_HEADER
    assert len(table) == 1 + 6
    log = ExportLog.objects.get()
    assert (
        log.export_type,
        log.school_id,
        log.school_count,
        log.row_count,
        log.filters,
    ) == (
        "all_children",
        None,
        2,
        6,
        {"status": "all"},
    )


def test_api_search_and_status(client, setup):
    response = client.get(
        URL, {"search": "pune", "status": "active"}, **auth_headers(setup["admin"])
    )

    rows = parse_csv(response)[1:]
    assert {r[COL["school_name"]] for r in rows} == {"Bravo School"}
    assert len(rows) == 2
    assert ExportLog.objects.get().filters == {"search": "pune", "status": "active"}


def test_api_co_gets_only_own_schools(client, setup):
    co = make_user("CO Full Time")
    Partner.objects.filter(pk=setup["alpha"].pk).update(co_id=co.user_id)

    rows = parse_csv(client.get(URL, **auth_headers(co)))[1:]

    assert {r[COL["school_name"]] for r in rows} == {"Alpha School"}


def test_api_cho_gets_only_worknode_schools(client, setup):
    cho = make_user("CHO", worknode_id=424242)
    PartnerWorknode.objects.create(partner_id=str(setup["bravo"].partner_id), worknode_id=424242)

    rows = parse_csv(client.get(URL, **auth_headers(cho)))[1:]

    assert {r[COL["school_name"]] for r in rows} == {"Bravo School"}


def test_api_no_schools_is_header_only(client, setup):
    response = client.get(URL, **auth_headers(make_user("CHO", worknode_id=None)))

    assert parse_csv(response) == [ALL_CHILDREN_HEADER]


def test_api_bad_status_is_422(client, setup):
    assert client.get(URL, {"status": "bogus"}, **auth_headers(setup["admin"])).status_code == 422
    assert ExportLog.objects.count() == 0


def test_api_no_active_year_is_404(client, setup):
    AcademicYear.objects.update(is_active=False)

    assert client.get(URL, **auth_headers(setup["admin"])).status_code == 404
    assert ExportLog.objects.count() == 0


def test_api_requires_auth(client, setup):
    assert client.get(URL).status_code == 401
