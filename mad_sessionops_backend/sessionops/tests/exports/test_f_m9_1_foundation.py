"""F-M9-1: Export foundation — CSV builder, audit log, export scope, search helper."""

import csv
import io
from datetime import date, datetime, time
from datetime import timezone as dt_timezone
from unittest.mock import patch

import pytest

from sessionops.models import ExportLog, Partner, PartnerWorknode, User
from sessionops.services.exports.audit import log_export
from sessionops.services.exports.csv_writer import build_csv_response, export_filename, safe_cell
from sessionops.services.exports.scope import export_school_ids
from sessionops.services.schools.queries import filter_schools_by_search

# ── Helpers ────────────────────────────────────────────────────────────────────

_UID = iter(range(9_500_000, 9_600_000))
_SID = iter(range(95_000, 96_000))


def _make_user(role: str, worknode_id: int | None = None) -> User:
    uid = next(_UID)
    return User.objects.create(
        user_login=f"u{uid}@test.com",
        user_display_name=f"User {uid}",
        email=f"u{uid}@test.com",
        user_role=role,
        is_active=True,
        worknode_id=worknode_id,
    )


def _make_school(
    co_id: int = 1, name: str | None = None, city: str = "", state: str = ""
) -> Partner:
    sid = next(_SID)
    return Partner.objects.create(
        partner_id=sid,
        partner_name=name or f"School {sid}",
        co_id=co_id,
        city=city,
        state=state,
        converted=True,
    )


def _parse(response) -> list[list[str]]:
    body = response.content.decode("utf-8")
    assert body.startswith("﻿")
    return list(csv.reader(io.StringIO(body[1:])))


# ── safe_cell ──────────────────────────────────────────────────────────────────


def test_safe_cell_none_is_empty():
    assert safe_cell(None) == ""


def test_safe_cell_date_time_formats():
    assert safe_cell(date(2026, 9, 27)) == "2026-09-27"
    assert safe_cell(time(10, 5, 30)) == "10:05"


def test_safe_cell_aware_datetime_rendered_in_ist():
    utc = datetime(2026, 9, 27, 4, 30, tzinfo=dt_timezone.utc)
    assert safe_cell(utc) == "2026-09-27 10:00"


def test_safe_cell_bool():
    assert safe_cell(True) == "yes"
    assert safe_cell(False) == "no"


@pytest.mark.parametrize("value", ["=SUM(A1)", "+919999999999", "-5", "@x", "\tcmd", "\rcmd"])
def test_safe_cell_escapes_formula_prefixes(value):
    assert safe_cell(value) == "'" + value


def test_safe_cell_plain_values_unchanged():
    assert safe_cell("Asha Kumari") == "Asha Kumari"
    assert safe_cell(42) == "42"
    assert safe_cell(-5) == "-5"  # numbers are not user text; left as-is


# ── build_csv_response ─────────────────────────────────────────────────────────


def test_build_csv_response_headers_and_body():
    response = build_csv_response(
        "children_1_2026-09-27.csv", ["id", "name"], [[1, "Asha"], [2, "Ravi"]]
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response["Content-Disposition"] == 'attachment; filename="children_1_2026-09-27.csv"'
    assert response["Cache-Control"] == "no-store"
    assert b"\r\n" in response.content
    assert _parse(response) == [["id", "name"], ["1", "Asha"], ["2", "Ravi"]]


def test_build_csv_response_zero_rows_still_has_header():
    response = build_csv_response("x.csv", ["id", "name"], [])
    assert _parse(response) == [["id", "name"]]


def test_build_csv_response_devanagari_round_trips():
    response = build_csv_response("x.csv", ["name"], [["आशा कुमारी"]])
    assert _parse(response)[1] == ["आशा कुमारी"]


def test_build_csv_response_escapes_cells():
    response = build_csv_response("x.csv", ["name"], [["=HYPERLINK(1)"]])
    assert _parse(response)[1] == ["'=HYPERLINK(1)"]


# ── export_filename ────────────────────────────────────────────────────────────


def test_export_filename_uses_ist_date():
    # 20:00 UTC on 26 Sep is 01:30 IST on 27 Sep
    fixed = datetime(2026, 9, 26, 20, 0, tzinfo=dt_timezone.utc)
    with patch("sessionops.services.exports.csv_writer.timezone.now", return_value=fixed):
        assert export_filename("children", 12345) == "children_12345_2026-09-27.csv"
        assert export_filename("schools", "all") == "schools_all_2026-09-27.csv"


# ── log_export ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_log_export_creates_row():
    user = _make_user("CO Full Time")

    log = log_export(user, "school_children", row_count=3, school_id=123, filters={"status": "all"})

    assert ExportLog.objects.count() == 1
    log.refresh_from_db()
    assert log.user_id_id == user.pk
    assert log.export_type == "school_children"
    assert log.school_id == 123
    assert log.filters == {"status": "all"}
    assert log.school_count == 1
    assert log.row_count == 3
    assert log.created_at is not None


@pytest.mark.django_db
def test_log_export_cross_school_defaults():
    user = _make_user("Function Lead")

    log = log_export(user, "schools_summary", row_count=0, school_count=0)

    assert log.school_id is None
    assert log.filters == {}
    assert log.school_count == 0


# ── filter_schools_by_search ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_filter_schools_by_search_matches_name_city_state():
    by_name = _make_school(name="Sunrise Public School")
    by_city = _make_school(city="Pune")
    by_state = _make_school(state="Karnataka")
    _make_school(name="Other", city="Delhi", state="Delhi")
    qs = Partner.objects.all()

    def ids(term):
        return set(filter_schools_by_search(qs, term).values_list("partner_id", flat=True))

    assert ids("sunrise") == {by_name.partner_id}
    assert ids("PUNE") == {by_city.partner_id}
    assert ids("karna") == {by_state.partner_id}


@pytest.mark.django_db
def test_filter_schools_by_search_blank_returns_queryset_unchanged():
    _make_school()
    _make_school()
    qs = Partner.objects.all()

    assert filter_schools_by_search(qs, None).count() == 2
    assert filter_schools_by_search(qs, "   ").count() == 2


# ── export_school_ids (R13 scope) ──────────────────────────────────────────────


@pytest.mark.django_db
def test_export_school_ids_co_sees_only_own_schools():
    co = _make_user("CO Full Time")
    own = _make_school(co_id=co.user_id)
    _make_school(co_id=co.user_id + 1)

    assert export_school_ids(co) == [own.partner_id]


@pytest.mark.django_db
def test_export_school_ids_cho_sees_only_worknode_schools():
    cho = _make_user("CHO", worknode_id=777)
    mapped = _make_school()
    _make_school()
    PartnerWorknode.objects.create(partner_id=str(mapped.partner_id), worknode_id=777)

    assert export_school_ids(cho) == [mapped.partner_id]


@pytest.mark.django_db
def test_export_school_ids_admin_sees_all_ordered_by_name():
    admin = _make_user("Project Lead")
    b = _make_school(name="Bravo School")
    a = _make_school(name="Alpha School")

    assert export_school_ids(admin) == [a.partner_id, b.partner_id]


@pytest.mark.django_db
def test_export_school_ids_search_narrows_scope():
    admin = _make_user("Function Lead")
    pune = _make_school(city="Pune")
    _make_school(city="Mumbai")

    assert export_school_ids(admin, "pune") == [pune.partner_id]


@pytest.mark.django_db
def test_export_school_ids_no_scope_is_empty():
    cho = _make_user("CHO", worknode_id=None)
    _make_school()

    assert export_school_ids(cho) == []
