"""F-M10-5: progression run model, school freeze, release."""

import re

from django.db import IntegrityError, transaction
from django.test import Client

import pytest

from sessionops.exceptions import ConflictError, NotFound
from sessionops.models import AcademicYear, ProgressionRun, SchoolProgression
from sessionops.services.progression.freeze import (
    frozen_school_ids,
    is_school_frozen,
    release_school,
)
from sessionops.services.rbac.scope import get_school_or_403, schools_visible_to
from sessionops.tests.exports.factories import (
    active_year,
    auth_headers,
    make_school,
    make_user,
    school_year,
)


@pytest.fixture
def setup(db):
    admin = make_user("Function Lead")
    year = active_year(admin)
    target, _ = AcademicYear.objects.get_or_create(
        label="2027-2028", defaults={"is_active": False, "created_by": admin}
    )
    co = make_user("CO Full Time")
    frozen, _ = make_school(co_id=co.user_id, name="Frozen School")
    other, _ = make_school(co_id=co.user_id, name="Normal School")
    run = ProgressionRun.objects.create(
        from_academic_year_id=year, to_academic_year_id=target, started_by=admin
    )
    sp = SchoolProgression.objects.create(
        run_id=run,
        school_id=frozen.partner_id,
        from_school_academic_year_id=school_year(frozen.partner_id, admin),
    )
    school_year(other.partner_id, admin)
    return {
        "admin": admin,
        "co": co,
        "frozen": frozen,
        "other": other,
        "run": run,
        "sp": sp,
    }


@pytest.fixture
def client():
    return Client()


def _set_status(sp, status):
    SchoolProgression.objects.filter(pk=sp.pk).update(status=status)


# ── Model + freeze service ─────────────────────────────────────────────────────


def test_second_unfinished_progression_for_school_rejected(setup):
    with pytest.raises(IntegrityError), transaction.atomic():
        SchoolProgression.objects.create(
            run_id=setup["run"],
            school_id=setup["frozen"].partner_id,
            from_school_academic_year_id=setup["sp"].from_school_academic_year_id,
        )


@pytest.mark.parametrize(
    "status,frozen",
    [
        ("queued", True),
        ("running", True),
        ("failed", True),
        ("completed", False),
        ("undone", False),
        ("released", False),
    ],
)
def test_frozen_statuses(setup, status, frozen):
    _set_status(setup["sp"], status)
    assert is_school_frozen(setup["frozen"].partner_id) is frozen
    assert (setup["frozen"].partner_id in frozen_school_ids()) is frozen


# ── Visibility ─────────────────────────────────────────────────────────────────


def test_frozen_school_hidden_from_co(setup):
    ids = set(schools_visible_to(setup["co"]).values_list("partner_id", flat=True))
    assert ids == {setup["other"].partner_id}
    with pytest.raises(NotFound):
        get_school_or_403(setup["co"], setup["frozen"].partner_id)


def test_frozen_school_visible_to_admin(setup):
    ids = set(schools_visible_to(setup["admin"]).values_list("partner_id", flat=True))
    assert setup["frozen"].partner_id in ids
    assert get_school_or_403(setup["admin"], setup["frozen"].partner_id) == setup["frozen"]


def test_school_list_reports_hidden_count(client, setup):
    body = client.get("/api/schools/", **auth_headers(setup["co"])).json()
    assert [s["partner_id"] for s in body["schools"]] == [setup["other"].partner_id]
    assert body["progressing_count"] == 1

    admin_body = client.get("/api/schools/", **auth_headers(setup["admin"])).json()
    assert admin_body["progressing_count"] == 0


def test_permissions_read_only_while_frozen(client, setup):
    url = f"/api/auth/me/permissions/?school_id={setup['frozen'].partner_id}"
    body = client.get(url, **auth_headers(setup["admin"])).json()
    assert body == {"can_view": True, "can_modify": False}

    _set_status(setup["sp"], "completed")
    body = client.get(url, **auth_headers(setup["admin"])).json()
    assert body["can_modify"] is True


# ── Write freeze (every real /api/schools/{id}/… route) ────────────────────────


def _school_write_paths(school_id: int) -> list[str]:
    from sessionops.routes import api

    paths = set()
    for pattern in api.urls[0]:
        route = str(pattern.pattern)
        if not route.startswith("api/schools/<school_id>/") and not route.startswith(
            "api/schools/<int:school_id>/"
        ):
            continue
        concrete = re.sub(r"<(?:int:)?school_id>", str(school_id), route)
        concrete = re.sub(r"<[^>]+>", "1", concrete)
        paths.add("/" + concrete)
    return sorted(paths)


def test_school_write_routes_exist(setup):
    paths = _school_write_paths(setup["frozen"].partner_id)
    # children, classes, buckets/sections, slots, slot-classes, session, holidays, exports…
    for fragment in ("children", "classes", "slots", "holidays", "session"):
        assert any(fragment in p for p in paths), fragment


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
def test_every_school_write_route_blocked_for_frozen_school(client, setup, method):
    headers = auth_headers(setup["admin"])  # even admins can't write
    for path in _school_write_paths(setup["frozen"].partner_id):
        resp = getattr(client, method)(path, {}, content_type="application/json", **headers)
        assert resp.status_code == 409, (method, path, resp.status_code)
        assert resp.json()["error"]["code"] == "school_progressing"


def test_reads_still_work_for_admin(client, setup):
    resp = client.get(
        f"/api/schools/{setup['frozen'].partner_id}/holidays/",
        **auth_headers(setup["admin"]),
    )
    assert resp.status_code == 200


def test_unfrozen_school_writes_not_blocked(client, setup):
    resp = client.post(
        f"/api/schools/{setup['other'].partner_id}/holidays/",
        {},
        content_type="application/json",
        **auth_headers(setup["admin"]),
    )
    assert resp.status_code != 409


def test_completed_school_is_writable_again(client, setup):
    _set_status(setup["sp"], "completed")
    resp = client.post(
        f"/api/schools/{setup['frozen'].partner_id}/holidays/",
        {},
        content_type="application/json",
        **auth_headers(setup["admin"]),
    )
    assert resp.status_code != 409


def test_non_school_routes_not_blocked(client, setup):
    # Sync / admin endpoints live outside /api/schools/ and are never frozen.
    resp = client.get("/api/admin/classes/", **auth_headers(setup["admin"]))
    assert resp.status_code == 200


# ── Release ────────────────────────────────────────────────────────────────────


def test_release_failed_school(setup):
    _set_status(setup["sp"], "failed")
    sp = release_school(setup["sp"], setup["admin"])

    assert sp.status == "released"
    assert not is_school_frozen(setup["frozen"].partner_id)
    setup["run"].refresh_from_db()
    assert setup["run"].status == "completed"


def test_release_non_failed_is_conflict(setup):
    with pytest.raises(ConflictError):
        release_school(setup["sp"], setup["admin"])  # queued


def test_release_endpoint(client, setup):
    _set_status(setup["sp"], "failed")
    url = (
        f"/api/admin/progression/runs/{setup['run'].run_id}"
        f"/schools/{setup['frozen'].partner_id}/release/"
    )

    assert client.post(url, **auth_headers(setup["co"])).status_code == 403
    resp = client.post(url, **auth_headers(setup["admin"]))
    assert resp.status_code == 200
    assert resp.json()["status"] == "released"

    again = client.post(url, **auth_headers(setup["admin"]))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "release_not_allowed"
