"""F-M9-5: Schools summary export — export search, bulk CHO lookup, summary rows, API."""

from datetime import date, time

from django.test import Client

import pytest

from sessionops.models import (
    AcademicYear,
    Child,
    ExportLog,
    Partner,
    PartnerWorknode,
    SchoolAcademicYear,
    SchoolSessionDetails,
)
from sessionops.services.exports.schools import SCHOOLS_HEADER, schools_summary_rows
from sessionops.services.exports.scope import export_school_ids, filter_schools_like_page
from sessionops.services.schools.queries import (
    get_chos_for_school,
    get_chos_for_schools,
    get_school_stats,
)
from sessionops.tests.exports.factories import (
    active_year,
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

# ── filter_schools_like_page (matches SchoolListPage.visibleSchools) ───────────


@pytest.fixture
def schools(db):
    return {
        "name": make_school(name="Sunrise Public School", city="Delhi", state="Delhi")[0],
        "city": make_school(name="Alpha", city="Pune", state="Maharashtra")[0],
        "co": make_school(name="Beta", city="Delhi", state="Delhi", co_name="Meera Iyer")[0],
        "state": make_school(name="Gamma", city="Mysuru", state="Karnataka")[0],
    }


def _ids(term) -> set[int]:
    return set(
        filter_schools_like_page(Partner.objects.all(), term).values_list("partner_id", flat=True)
    )


def test_matches_name_city_and_co_name(schools):
    assert _ids("sunrise") == {schools["name"].partner_id}
    assert _ids("PUNE") == {schools["city"].partner_id}
    assert _ids("meera") == {schools["co"].partner_id}


def test_does_not_match_state_like_the_page(schools):
    assert _ids("karnataka") == set()


def test_blank_search_is_no_filter(schools):
    assert _ids(None) == _ids("") == _ids("   ") == {s.partner_id for s in schools.values()}


def test_untrimmed_text_is_matched_as_typed(schools):
    # Page: "pune ".trim() is non-blank, then matches the raw "pune " — no city contains it.
    assert _ids("pune ") == set()


def test_api_school_search_keeps_m1_state_behaviour(schools):
    """GET /api/schools/?search= is untouched (TC-M1-4-06)."""
    from sessionops.services.schools.queries import filter_schools_by_search

    matched = filter_schools_by_search(Partner.objects.all(), "karnataka")
    assert set(matched.values_list("partner_id", flat=True)) == {schools["state"].partner_id}


def test_export_school_ids_uses_page_search(schools):
    admin = make_user("Function Lead")
    assert export_school_ids(admin, "meera") == [schools["co"].partner_id]
    assert export_school_ids(admin, "karnataka") == []


# ── get_chos_for_schools ───────────────────────────────────────────────────────


@pytest.fixture
def cho_setup(db):
    a, wid_a = make_school(name="A")
    b, wid_b = make_school(name="B")
    shared = make_school(name="Shared")[0]
    PartnerWorknode.objects.create(partner_id=str(shared.partner_id), worknode_id=wid_a)
    return {
        "a": a,
        "b": b,
        "shared": shared,
        "cho_a": make_user("CHO", wid_a, name="Chandra"),
        "cho_b": make_user("CO Part Time,CHO", wid_b, name="Bhavna"),
        "not_cho": make_user("Wingman", wid_a, name="Wing"),
        "inactive": make_user("CHO", wid_a, name="Old", is_active=False),
        "none": make_school(name="No CHO")[0],
    }


def test_bulk_chos_per_school(cho_setup):
    s = cho_setup
    result = get_chos_for_schools(
        [
            s["a"].partner_id,
            s["b"].partner_id,
            s["shared"].partner_id,
            s["none"].partner_id,
        ]
    )

    names = {pid: [u.user_display_name for u in users] for pid, users in result.items()}
    assert names[s["a"].partner_id] == ["Chandra"]
    assert names[s["b"].partner_id] == ["Bhavna"]  # multi-role string parsed
    assert names[s["shared"].partner_id] == ["Chandra"]  # worknode shared with A
    assert names[s["none"].partner_id] == []


def test_single_school_wrapper_matches_bulk(cho_setup):
    s = cho_setup
    for key in ("a", "b", "shared", "none"):
        pid = s[key].partner_id
        assert [u.pk for u in get_chos_for_school(pid)] == [
            u.pk for u in get_chos_for_schools([pid])[pid]
        ]


def test_bulk_chos_query_count(cho_setup, django_assert_max_num_queries):
    ids = [cho_setup[k].partner_id for k in ("a", "b", "shared", "none")]
    with django_assert_max_num_queries(2):
        get_chos_for_schools(ids)


def test_bulk_chos_empty_input(db):
    assert get_chos_for_schools([]) == {}


# ── schools_summary_rows ───────────────────────────────────────────────────────

COL = {name: i for i, name in enumerate(SCHOOLS_HEADER)}


def _child(school_id, admin, name, **kw):
    return Child.objects.create(
        school_id=school_id,
        first_name=name,
        last_name="X",
        gender="male",
        age=9,
        created_by=admin,
        **kw,
    )


@pytest.fixture
def summary(db):
    admin = make_user("Function Lead")
    year = active_year(admin)
    full, wid = make_school(
        name="Bravo School",
        city="Pune",
        state="Maharashtra",
        co_name="Meera",
        mou_start_date=date(2026, 6, 1),
        mou_end_date=date(2027, 5, 31),
    )
    pid = full.partner_id
    bucket = make_bucket(pid, admin, "Group A", class_code="5")
    make_bucket(pid, admin, "Circle", class_code=None)
    place_child(bucket, admin, "Anu")
    place_child(bucket, admin, "Bala")
    _child(pid, admin, "Gone", is_active=False)
    _child(pid, admin, "Deleted", is_active=False, removed=True)
    slot = make_slot(pid, admin, "monday", time(10, 0), time(11, 0))
    make_slot(pid, admin, "tuesday")
    make_slot_class(slot, bucket, admin)
    make_user("Wingman", wid, name="Vol 1")
    make_user("CHO", wid, name="Chandra")
    SchoolSessionDetails.objects.create(
        school_id=pid,
        school_academic_year=school_year(pid, admin),
        start_date=date(2026, 7, 1),
        end_date=date(2027, 3, 31),
        created_by=admin,
    )
    empty = make_school(name="Alpha School")[0]
    return {"admin": admin, "year": year, "full": full, "empty": empty}


def test_summary_row_values(summary):
    row = schools_summary_rows([summary["full"].partner_id])[0]

    assert row[COL["school_name"]] == "Bravo School"
    assert (row[COL["city"]], row[COL["state"]], row[COL["co_name"]]) == (
        "Pune",
        "Maharashtra",
        "Meera",
    )
    assert row[COL["cho_names"]] == "Chandra"
    assert row[COL["academic_year"]] == "2026-2027"
    assert row[COL["active_children"]] == 2
    assert row[COL["inactive_children"]] == 1  # removed child not counted
    assert row[COL["volunteers"]] == 2  # every active user on the worknode, like the page
    assert row[COL["classes"]] == 1
    assert row[COL["buckets"]] == 2
    assert row[COL["slots"]] == 2
    assert row[COL["slot_classes"]] == 1
    assert (row[COL["term_start"]], row[COL["term_end"]]) == (
        date(2026, 7, 1),
        date(2027, 3, 31),
    )
    assert (row[COL["mou_start_date"]], row[COL["mou_end_date"]]) == (
        date(2026, 6, 1),
        date(2027, 5, 31),
    )


def test_page_counts_come_from_get_school_stats(summary):
    pid = summary["full"].partner_id
    stats = get_school_stats([pid])[pid]
    row = schools_summary_rows([pid])[0]

    assert row[COL["active_children"]] == stats["children_count"]
    assert row[COL["volunteers"]] == stats["volunteers_count"]
    assert row[COL["classes"]] == stats["classes_count"]
    assert row[COL["slot_classes"]] == stats["assignments_count"]


def test_empty_school_has_zero_counts_and_blank_dates(summary):
    row = schools_summary_rows([summary["empty"].partner_id])[0]

    assert row[COL["active_children"]] == row[COL["slots"]] == row[COL["buckets"]] == 0
    assert (row[COL["term_start"]], row[COL["term_end"]], row[COL["cho_names"]]) == (
        None,
        None,
        "",
    )


def test_term_dates_on_archived_school_year_ignored(summary):
    """F-M10-3: term dates come from the school's own ACTIVE school-year only."""
    admin = summary["admin"]
    other = AcademicYear.objects.create(label="2025-2026", is_active=False, created_by=admin)
    archived = SchoolAcademicYear.objects.create(
        school_id=summary["empty"].partner_id,
        academic_year_id=other,
        is_active=False,
        created_by=admin,
    )
    SchoolSessionDetails.objects.create(
        school_id=summary["empty"].partner_id,
        school_academic_year=archived,
        start_date=date(2025, 7, 1),
        end_date=date(2026, 3, 31),
        created_by=admin,
    )

    row = schools_summary_rows([summary["empty"].partner_id])[0]

    assert row[COL["term_start"]] is None


def test_school_on_older_year_shows_its_own_term_dates(summary):
    """F-M10-3: a school not yet progressed (active school-year on 2025-26) keeps its data."""
    admin = summary["admin"]
    older = AcademicYear.objects.create(label="2025-2026", is_active=False, created_by=admin)
    say = school_year(summary["empty"].partner_id, admin)
    say.academic_year_id = older
    say.save()
    SchoolSessionDetails.objects.create(
        school_id=summary["empty"].partner_id,
        school_academic_year=say,
        start_date=date(2025, 7, 1),
        end_date=date(2026, 3, 31),
        created_by=admin,
    )

    row = schools_summary_rows([summary["empty"].partner_id])[0]

    assert row[COL["term_start"]] == date(2025, 7, 1)


def test_rows_follow_given_order(summary):
    ids = [summary["empty"].partner_id, summary["full"].partner_id]
    assert [r[COL["partner_id"]] for r in schools_summary_rows(ids)] == ids


def test_empty_ids(summary):
    assert schools_summary_rows([]) == []


def test_query_count_is_constant(summary, django_assert_max_num_queries):
    ids = [summary["full"].partner_id, summary["empty"].partner_id]
    with django_assert_max_num_queries(16) as few:
        schools_summary_rows(ids)
    baseline = len(few.captured_queries)

    for n in range(6):
        ids.append(make_school(name=f"Extra {n}")[0].partner_id)
    with django_assert_max_num_queries(baseline):
        rows = schools_summary_rows(ids)

    assert len(rows) == 8


def test_row_width_matches_header(summary):
    for row in schools_summary_rows([summary["full"].partner_id]):
        assert len(row) == len(SCHOOLS_HEADER)


# ── API ────────────────────────────────────────────────────────────────────────

URL = "/api/exports/schools.csv"


@pytest.fixture
def client():
    return Client()


def test_api_admin_gets_all_schools_ordered_by_name(client, summary):
    response = client.get(URL, **auth_headers(summary["admin"]))

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith('attachment; filename="schools_all_')
    table = parse_csv(response)
    assert table[0] == SCHOOLS_HEADER
    assert [r[COL["school_name"]] for r in table[1:]] == [
        "Alpha School",
        "Bravo School",
    ]
    log = ExportLog.objects.get()
    assert (
        log.export_type,
        log.school_id,
        log.school_count,
        log.row_count,
        log.filters,
    ) == (
        "schools_summary",
        None,
        2,
        2,
        {},
    )


def test_api_search_matches_page_and_is_logged(client, summary):
    response = client.get(URL, {"search": "meera"}, **auth_headers(summary["admin"]))

    assert [r[COL["school_name"]] for r in parse_csv(response)[1:]] == ["Bravo School"]
    assert ExportLog.objects.get().filters == {"search": "meera"}


def test_api_co_sees_only_own_schools(client, summary):
    co = make_user("CO Full Time")
    Partner.objects.filter(pk=summary["empty"].pk).update(co_id=co.user_id)

    table = parse_csv(client.get(URL, **auth_headers(co)))

    assert [r[COL["school_name"]] for r in table[1:]] == ["Alpha School"]


def test_api_user_without_schools_gets_header_only(client, summary):
    cho = make_user("CHO", worknode_id=None)

    response = client.get(URL, **auth_headers(cho))

    assert parse_csv(response) == [SCHOOLS_HEADER]
    assert ExportLog.objects.get().school_count == 0


def test_api_no_active_year_is_404(client, summary):
    AcademicYear.objects.update(is_active=False)

    assert client.get(URL, **auth_headers(summary["admin"])).status_code == 404
    assert ExportLog.objects.count() == 0


def test_api_requires_auth(client, summary):
    assert client.get(URL).status_code == 401
