"""F-M9-3: School volunteer roster export — service + API."""

import csv
import io
from datetime import time

from django.test import Client

import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from sessionops.models import (
    AcademicYear,
    Class,
    ClassSection,
    ClassSectionSubject,
    ExportLog,
    Partner,
    PartnerWorknode,
    Program,
    SchoolAcademicYear,
    SchoolClass,
    Slot,
    SlotClassSection,
    SlotClassSectionVolunteer,
    Subject,
    User,
)
from sessionops.services.exports.volunteers import (
    VOLUNTEERS_HEADER,
    school_volunteer_rows,
    volunteer_rows_for_schools,
)
from sessionops.services.volunteers.list import list_school_volunteers

# ── Helpers ────────────────────────────────────────────────────────────────────

_UID = iter(range(9_700_000, 9_800_000))
_SID = iter(range(97_000, 98_000))
_WID = iter(range(970_000, 980_000))

COL = {name: i for i, name in enumerate(VOLUNTEERS_HEADER)}


def _make_user(role: str = "Function Lead", worknode_id: int | None = None, **kw) -> User:
    uid = next(_UID)
    return User.objects.create(
        user_display_name=kw.pop("name", f"User {uid}"),
        user_login=f"m93_{uid}@t.com",
        email=f"m93_{uid}@t.com",
        user_role=role,
        is_active=kw.pop("is_active", True),
        worknode_id=worknode_id,
        **kw,
    )


def _make_school(co_id: int = 1) -> tuple[Partner, int]:
    """School plus its own worknode mapping; returns (partner, worknode_id)."""
    sid = next(_SID)
    partner = Partner.objects.create(
        partner_id=sid, partner_name=f"School {sid}", co_id=co_id, converted=True
    )
    wid = next(_WID)
    PartnerWorknode.objects.create(partner_id=str(sid), worknode_id=wid)
    return partner, wid


def _say(school_id: int, admin: User) -> SchoolAcademicYear:
    year, _ = AcademicYear.objects.get_or_create(
        label="2026-2027", defaults={"is_active": True, "created_by": admin}
    )
    say, _ = SchoolAcademicYear.objects.get_or_create(
        school_id=school_id, academic_year_id=year, defaults={"created_by": admin}
    )
    return say


def _bucket(school_id: int, admin: User, with_class: bool = True) -> ClassSection:
    school_class = None
    if with_class:
        program, _ = Program.objects.get_or_create(
            program_id=1,
            defaults={"program_name": "Foundation Program", "is_active": True},
        )
        cls, _ = Class.objects.get_or_create(
            class_code="5",
            defaults={"class_name": "5th", "program_id": program, "is_active": True},
        )
        school_class, _ = SchoolClass.objects.get_or_create(
            school_id=school_id,
            school_academic_year_id=_say(school_id, admin),
            class_id_id=cls.class_id,
            defaults={"created_by": admin},
        )
    code = next(_UID)
    return ClassSection.objects.create(
        school_class_id=school_class,
        school_id=school_id,
        section_code=None,  # buckets carry no single-letter section code
        section_name=f"group_{code}",
        section_display_name="Group A",
        school_academic_year_id=_say(school_id, admin),
        created_by=admin,
    )


def _slot_class(
    school_id: int,
    admin: User,
    *,
    day: str = "monday",
    start: time = time(10, 0),
    end: time = time(11, 0),
    with_class: bool = True,
    subject: str = "English",
) -> SlotClassSection:
    slot = Slot.objects.create(
        school_id=school_id,
        school_academic_year_id=_say(school_id, admin),
        slot_name=f"{day} {start:%H:%M}",
        day_of_week=day,
        start_time=start,
        end_time=end,
        created_by=admin,
    )
    section = _bucket(school_id, admin, with_class=with_class)
    program, _ = Program.objects.get_or_create(
        program_id=1, defaults={"program_name": "Foundation Program", "is_active": True}
    )
    subj, _ = Subject.objects.get_or_create(subject_name=subject, defaults={"program_id": program})
    css = ClassSectionSubject.objects.create(
        class_section_id=section, subject_id=subj, created_by=admin
    )
    return SlotClassSection.objects.create(
        slot_id=slot,
        class_section_id=section,
        class_section_subject_id=css,
        created_by=admin,
    )


def _assign(scs: SlotClassSection, volunteer: User, admin: User, **kw) -> SlotClassSectionVolunteer:
    return SlotClassSectionVolunteer.objects.create(
        slot_class_section_id=scs, volunteer_id=volunteer, created_by=admin, **kw
    )


@pytest.fixture
def setup(db):
    """One school, two volunteers on its worknode: Asha assigned (Mon 10-11 English), Ravi not."""
    admin = _make_user("Function Lead")
    partner, wid = _make_school()
    asha = _make_user("Wingman", wid, name="Asha", contact="+919999900000", city="Pune")
    ravi = _make_user("Wingman", wid, name="Ravi")
    scs = _slot_class(partner.partner_id, admin)
    _assign(scs, asha, admin)
    return {
        "admin": admin,
        "partner": partner,
        "wid": wid,
        "asha": asha,
        "ravi": ravi,
        "scs": scs,
    }


def _by_name(rows) -> dict[str, list]:
    return {r[COL["name"]]: r for r in rows}


# ── Service ────────────────────────────────────────────────────────────────────


def test_rows_for_assigned_and_unassigned_volunteers(setup):
    rows = school_volunteer_rows(setup["partner"].partner_id)

    assert [r[COL["name"]] for r in rows] == ["Asha", "Ravi"]
    asha, ravi = rows
    assert asha[COL["slot_class_count"]] == 1
    assert asha[COL["assignments"]] == "Monday 10:00-11:00 · 5th · Group A · English"
    assert asha[COL["contact"]] == "+919999900000"
    assert asha[COL["city"]] == "Pune"
    assert asha[COL["role"]] == "Wingman"
    assert ravi[COL["slot_class_count"]] == 0
    assert ravi[COL["assignments"]] == ""


def test_classless_bucket_omits_class_segment(setup):
    scs = _slot_class(setup["partner"].partner_id, setup["admin"], day="tuesday", with_class=False)
    _assign(scs, setup["ravi"], setup["admin"])

    ravi = _by_name(school_volunteer_rows(setup["partner"].partner_id))["Ravi"]

    assert ravi[COL["assignments"]] == "Tuesday 10:00-11:00 · Group A · English"


def test_multiple_assignments_ordered_by_day_and_time(setup):
    later = _slot_class(setup["partner"].partner_id, setup["admin"], day="friday")
    earlier = _slot_class(
        setup["partner"].partner_id,
        setup["admin"],
        day="monday",
        start=time(8, 0),
        end=time(9, 0),
    )
    _assign(later, setup["asha"], setup["admin"])
    _assign(earlier, setup["asha"], setup["admin"])

    asha = _by_name(school_volunteer_rows(setup["partner"].partner_id))["Asha"]

    assert asha[COL["slot_class_count"]] == 3
    assert asha[COL["assignments"]].split("; ")[0].startswith("Monday 08:00-09:00")
    assert asha[COL["assignments"]].split("; ")[-1].startswith("Friday")


def test_subject_name_is_normalized(setup):
    scs = _slot_class(setup["partner"].partner_id, setup["admin"], subject="Foundation Day 1")
    _assign(scs, setup["ravi"], setup["admin"])

    ravi = _by_name(school_volunteer_rows(setup["partner"].partner_id))["Ravi"]

    assert ravi[COL["assignments"]].endswith("· Foundation")


def test_inactive_user_excluded(setup):
    _make_user("Wingman", setup["wid"], name="Gone", is_active=False)
    assert "Gone" not in _by_name(school_volunteer_rows(setup["partner"].partner_id))


def test_user_on_other_worknode_excluded(setup):
    _make_user("Wingman", setup["wid"] + 50_000, name="Elsewhere")
    assert "Elsewhere" not in _by_name(school_volunteer_rows(setup["partner"].partner_id))


@pytest.mark.parametrize("target", ["assignment", "slot_class", "slot"])
def test_soft_deleted_layers_not_listed(setup, target):
    scs = setup["scs"]
    if target == "assignment":
        SlotClassSectionVolunteer.objects.filter(slot_class_section_id=scs).update(
            is_active=False, removed=True
        )
    elif target == "slot_class":
        SlotClassSection.objects.filter(pk=scs.pk).update(is_active=False, removed=True)
    else:
        Slot.objects.filter(pk=scs.slot_id_id).update(is_active=False, removed=True)

    asha = _by_name(school_volunteer_rows(setup["partner"].partner_id))["Asha"]

    assert asha[COL["slot_class_count"]] == 0


def test_assignment_at_other_school_not_listed_here(setup):
    other, _ = _make_school()
    PartnerWorknode.objects.create(partner_id=str(other.partner_id), worknode_id=setup["wid"])
    scs = _slot_class(other.partner_id, setup["admin"], day="wednesday")
    _assign(scs, setup["ravi"], setup["admin"])

    here = _by_name(school_volunteer_rows(setup["partner"].partner_id))["Ravi"]
    there = _by_name(school_volunteer_rows(other.partner_id))["Ravi"]

    assert here[COL["slot_class_count"]] == 0
    assert there[COL["slot_class_count"]] == 1


def test_counts_match_volunteers_tab(setup):
    pid = setup["partner"].partner_id
    tab = {
        v["user_id"]: v["active_slot_class_count"]
        for v in list_school_volunteers(pid, setup["admin"])["volunteers"]
    }
    export = {r[COL["user_id"]]: r[COL["slot_class_count"]] for r in school_volunteer_rows(pid)}

    assert export == tab


def test_school_without_worknode_returns_no_rows(db):
    partner = Partner.objects.create(
        partner_id=next(_SID), partner_name="No WN", co_id=1, converted=True
    )
    assert school_volunteer_rows(partner.partner_id) == []
    assert volunteer_rows_for_schools([]) == {}


def test_multi_school_query_count_is_constant(setup, django_assert_max_num_queries):
    ids = [setup["partner"].partner_id]
    for _ in range(2):
        p, wid = _make_school()
        for n in range(3):
            v = _make_user("Wingman", wid, name=f"V{n}")
            _assign(_slot_class(p.partner_id, setup["admin"]), v, setup["admin"])
        ids.append(p.partner_id)

    with django_assert_max_num_queries(3):
        rows = volunteer_rows_for_schools(ids)

    assert sum(len(r) for r in rows.values()) == 2 + 6


def test_row_width_matches_header(setup):
    for row in school_volunteer_rows(setup["partner"].partner_id):
        assert len(row) == len(VOLUNTEERS_HEADER)


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
    return f"/api/schools/{school_id}/exports/volunteers.csv"


def _parse(response) -> list[list[str]]:
    body = response.content.decode("utf-8")
    assert body.startswith("﻿")
    return list(csv.reader(io.StringIO(body[1:])))


@pytest.fixture
def client():
    return Client()


def test_api_returns_csv_and_logs(client, setup):
    pid = setup["partner"].partner_id

    response = client.get(_url(pid), **_headers(setup["admin"]))

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith(f'attachment; filename="volunteers_{pid}_')
    table = _parse(response)
    assert table[0] == VOLUNTEERS_HEADER
    assert [r[COL["name"]] for r in table[1:]] == ["Asha", "Ravi"]
    assert table[1][COL["contact"]] == "'+919999900000"  # formula-safe
    log = ExportLog.objects.get()
    assert (log.export_type, log.school_id, log.row_count, log.filters) == (
        "school_volunteers",
        pid,
        2,
        {},
    )


def test_api_co_cannot_export_other_school(client, setup):
    other_co = _make_user("CO Full Time")

    response = client.get(_url(setup["partner"].partner_id), **_headers(other_co))

    assert response.status_code == 403
    assert ExportLog.objects.count() == 0


def test_api_unknown_school_is_404(client, setup):
    assert client.get(_url(999_999_999), **_headers(setup["admin"])).status_code == 404


def test_api_no_active_year_is_404(client, setup):
    AcademicYear.objects.update(is_active=False)

    response = client.get(_url(setup["partner"].partner_id), **_headers(setup["admin"]))

    assert response.status_code == 404
    assert ExportLog.objects.count() == 0


def test_api_requires_auth(client, setup):
    assert client.get(_url(setup["partner"].partner_id)).status_code == 401
