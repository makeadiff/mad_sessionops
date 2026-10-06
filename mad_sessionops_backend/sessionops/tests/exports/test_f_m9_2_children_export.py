"""F-M9-2: School children roster export — service + API."""

import csv
import io

from django.test import Client

import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from sessionops.models import (
    AcademicYear,
    Child,
    ChildRemovalLog,
    Class,
    ClassSection,
    ExportLog,
    Partner,
    Program,
    SchoolAcademicYear,
    SchoolClass,
    User,
)
from sessionops.schemas.children import ChildEnrollIn, DeactivateIn
from sessionops.services.children.deactivate import deactivate_child
from sessionops.services.children.enroll import enroll_child
from sessionops.services.children.queries import list_children
from sessionops.services.exports.children import CHILDREN_HEADER, school_children_rows

# ── Helpers ────────────────────────────────────────────────────────────────────

_UID = iter(range(9_600_000, 9_700_000))
_SID = iter(range(96_000, 97_000))

COL = {name: i for i, name in enumerate(CHILDREN_HEADER)}


def _make_user(role: str = "Function Lead") -> User:
    uid = next(_UID)
    return User.objects.create(
        user_display_name=f"User {uid}",
        user_login=f"m92_{uid}@t.com",
        email=f"m92_{uid}@t.com",
        user_role=role,
        is_active=True,
    )


def _make_partner(co_id: int = 1) -> Partner:
    sid = next(_SID)
    return Partner.objects.create(
        partner_id=sid, partner_name=f"School {sid}", co_id=co_id, converted=True
    )


def _year(user: User) -> AcademicYear:
    year, _ = AcademicYear.objects.get_or_create(
        label="2026-2027", defaults={"is_active": True, "created_by": user}
    )
    return year


def _make_class(school_id: int, user: User, class_code: str = "5") -> SchoolClass:
    program, _ = Program.objects.get_or_create(
        program_id=1, defaults={"program_name": "Foundation Program", "is_active": True}
    )
    cls, _ = Class.objects.get_or_create(
        class_code=class_code,
        defaults={
            "class_name": f"{class_code}th",
            "program_id": program,
            "is_active": True,
        },
    )
    say, _ = SchoolAcademicYear.objects.get_or_create(
        school_id=school_id, academic_year_id=_year(user), defaults={"created_by": user}
    )
    sc, _ = SchoolClass.objects.get_or_create(
        school_id=school_id,
        school_academic_year_id=say,
        class_id_id=cls.class_id,
        defaults={"created_by": user},
    )
    return sc


def _make_section(school_class: SchoolClass, user: User, code: str = "A") -> ClassSection:
    return ClassSection.objects.create(
        school_class_id=school_class,
        school_id=school_class.school_id,
        section_code=code,
        section_name=f"Section {code}",
        section_display_name=f"Group {code}",
        created_by=user,
    )


def _enroll(
    school_class: SchoolClass, user: User, section: ClassSection | None = None, **kwargs
) -> Child:
    data = dict(
        first_name="Asha",
        last_name="Kumar",
        gender="female",
        age=10,
        school_class_id=school_class.school_class_id,
        class_section_id=section.class_section_id if section else None,
    )
    data.update(kwargs)
    return enroll_child(school_class.school_id, ChildEnrollIn(**data), user)


def _ids(rows) -> list[int]:
    return [r[COL["child_id"]] for r in rows]


@pytest.fixture
def school(db):
    """School with one class, one bucket, 3 active children and 1 inactive."""
    user = _make_user()
    partner = _make_partner()
    sc = _make_class(partner.partner_id, user)
    bucket = _make_section(sc, user)
    active = [
        _enroll(sc, user, bucket, first_name="Bina"),
        _enroll(sc, user, bucket, first_name="Anil"),
        _enroll(sc, user, None, first_name="Chetan"),  # class, no bucket
    ]
    gone = _enroll(sc, user, bucket, first_name="Dev")
    deactivate_child(
        gone.child_id,
        DeactivateIn(removed_reason="transferred", other_details="Moved to Pune"),
        user,
    )
    return {
        "user": user,
        "partner": partner,
        "class": sc,
        "bucket": bucket,
        "active": active,
        "gone": gone,
    }


# ── Service: status filter ─────────────────────────────────────────────────────


def test_status_all_includes_active_and_inactive(school):
    rows = school_children_rows(school["partner"].partner_id, status="all")
    assert len(rows) == 4


def test_status_active_excludes_inactive(school):
    rows = school_children_rows(school["partner"].partner_id, status="active")
    assert school["gone"].child_id not in _ids(rows)
    assert len(rows) == 3


def test_status_inactive_row_has_removal_details(school):
    rows = school_children_rows(school["partner"].partner_id, status="inactive")

    assert _ids(rows) == [school["gone"].child_id]
    row = rows[0]
    assert row[COL["status"]] == "inactive"
    assert row[COL["removed_reason"]] == "Transferred to another school"
    assert row[COL["removal_details"]] == "Moved to Pune"
    assert row[COL["removed_on"]] is not None


def test_active_rows_have_empty_removal_columns(school):
    rows = school_children_rows(school["partner"].partner_id, status="active")
    for row in rows:
        assert row[COL["status"]] == "active"
        assert row[COL["removed_reason"]] is None
        assert row[COL["removal_details"]] is None
        assert row[COL["removed_on"]] is None


def test_removed_children_never_exported(school):
    Child.objects.filter(pk=school["active"][0].pk).update(removed=True)

    rows = school_children_rows(school["partner"].partner_id, status="all")

    assert school["active"][0].child_id not in _ids(rows)


# ── Service: placement + other filters (parity with list_children) ────────────


def test_class_and_bucket_columns(school):
    rows = {r[COL["first_name"]]: r for r in school_children_rows(school["partner"].partner_id)}

    assert rows["Bina"][COL["class"]] == "5th"
    assert rows["Bina"][COL["bucket"]] == "Group A"
    assert rows["Chetan"][COL["class"]] == "5th"
    assert rows["Chetan"][COL["bucket"]] is None


def test_unassigned_returns_only_children_without_bucket(school):
    pid = school["partner"].partner_id
    rows = school_children_rows(pid, status="active", unassigned=True)
    assert _ids(rows) == [school["active"][2].child_id]


@pytest.mark.parametrize(
    "filters",
    [
        {"status": "all"},
        {"status": "active", "search": "an"},
        {"status": "all", "unassigned": True},
    ],
)
def test_row_count_matches_list_children(school, filters):
    pid = school["partner"].partner_id
    assert len(school_children_rows(pid, **filters)) == list_children(pid, **filters).count()


def test_class_and_section_filters_match_list_children(school):
    pid = school["partner"].partner_id
    by_section = dict(status="all", section_id=school["bucket"].class_section_id)
    by_class = dict(status="all", class_id=school["class"].school_class_id)

    assert set(_ids(school_children_rows(pid, **by_section))) == {
        c.child_id for c in list_children(pid, **by_section)
    }
    assert set(_ids(school_children_rows(pid, **by_class))) == {
        c.child_id for c in list_children(pid, **by_class)
    }


def test_search_matches_first_or_last_name(school):
    pid = school["partner"].partner_id
    _enroll(school["class"], school["user"], None, first_name="Zoya", last_name="Rahman")

    assert len(school_children_rows(pid, search="rahman")) == 1
    assert len(school_children_rows(pid, search="zoya")) == 1


def test_ordering_class_then_bucket_then_name(school):
    rows = school_children_rows(school["partner"].partner_id, status="active")
    # Same class; bucketed children first (Anil, Bina), then no-bucket (Chetan).
    assert [r[COL["first_name"]] for r in rows] == ["Anil", "Bina", "Chetan"]


def test_unknown_reason_code_falls_back_to_raw(school):
    ChildRemovalLog.objects.filter(child_id=school["gone"].child_id).update(
        removed_reason="legacy_code"
    )
    rows = school_children_rows(school["partner"].partner_id, status="inactive")
    assert rows[0][COL["removed_reason"]] == "legacy_code"


def test_retired_removal_log_is_ignored(school):
    # reactivate_child retires the log this way; the child row reads as having no reason.
    ChildRemovalLog.objects.filter(child_id=school["gone"].child_id).update(
        is_active=False, removed=True
    )
    rows = school_children_rows(school["partner"].partner_id, status="inactive")
    assert rows[0][COL["removed_reason"]] is None


def test_gender_uses_display_label(school):
    rows = school_children_rows(school["partner"].partner_id)
    assert {r[COL["gender"]] for r in rows} == {"Female"}


def test_row_width_matches_header(school):
    for row in school_children_rows(school["partner"].partner_id):
        assert len(row) == len(CHILDREN_HEADER)


# ── API ────────────────────────────────────────────────────────────────────────


def _headers(user: User) -> dict:
    r = RefreshToken()
    for claim, attr in (
        ("user_id", "user_id"),
        ("email", "email"),
        ("role", "user_role"),
    ):
        r[claim] = getattr(user, attr)
        r.access_token[claim] = getattr(user, attr)
    return {"HTTP_AUTHORIZATION": f"Bearer {r.access_token}"}


def _url(school_id: int) -> str:
    return f"/api/schools/{school_id}/exports/children.csv"


def _parse(response) -> list[list[str]]:
    body = response.content.decode("utf-8")
    assert body.startswith("﻿")
    return list(csv.reader(io.StringIO(body[1:])))


@pytest.fixture
def client():
    return Client()


def test_api_returns_csv_for_school(client, school):
    pid = school["partner"].partner_id
    response = client.get(_url(pid), **_headers(school["user"]))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response["Content-Disposition"].startswith(f'attachment; filename="children_{pid}_')
    table = _parse(response)
    assert table[0] == CHILDREN_HEADER
    assert len(table) == 1 + 4  # default status=all


def test_api_applies_tab_filters(client, school):
    pid = school["partner"].partner_id
    response = client.get(
        _url(pid),
        {"status": "active", "unassigned": "true"},
        **_headers(school["user"]),
    )

    rows = _parse(response)[1:]
    assert [r[COL["first_name"]] for r in rows] == ["Chetan"]


def test_api_writes_one_audit_row_with_non_empty_filters(client, school):
    pid = school["partner"].partner_id
    client.get(_url(pid), {"status": "inactive", "search": ""}, **_headers(school["user"]))

    log = ExportLog.objects.get()
    assert log.user_id_id == school["user"].pk
    assert log.export_type == "school_children"
    assert log.school_id == pid
    assert log.row_count == 1
    assert log.filters == {"status": "inactive"}


def test_api_co_cannot_export_other_school(client, school):
    other_co = _make_user("CO Full Time")  # partner.co_id=1, not this CO

    response = client.get(_url(school["partner"].partner_id), **_headers(other_co))

    assert response.status_code == 403
    assert ExportLog.objects.count() == 0


def test_api_co_can_export_own_school(client, school):
    co = _make_user("CO Full Time")
    Partner.objects.filter(pk=school["partner"].pk).update(co_id=co.user_id)

    response = client.get(_url(school["partner"].partner_id), **_headers(co))

    assert response.status_code == 200


def test_api_unknown_school_is_404(client, school):
    response = client.get(_url(999_999_999), **_headers(school["user"]))

    assert response.status_code == 404
    assert ExportLog.objects.count() == 0


def test_api_no_active_year_is_404(client, school):
    AcademicYear.objects.update(is_active=False)

    response = client.get(_url(school["partner"].partner_id), **_headers(school["user"]))

    assert response.status_code == 404
    assert ExportLog.objects.count() == 0


def test_api_invalid_status_is_rejected(client, school):
    response = client.get(
        _url(school["partner"].partner_id),
        {"status": "bogus"},
        **_headers(school["user"]),
    )

    assert response.status_code == 422
    assert ExportLog.objects.count() == 0


def test_api_requires_auth(client, school):
    response = client.get(_url(school["partner"].partner_id))

    assert response.status_code == 401
