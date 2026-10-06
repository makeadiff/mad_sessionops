"""F-M10-1: Class catalog admin — seed, rules, enrolment switch, admin + public API."""

import importlib
from types import SimpleNamespace

from django.apps import apps as django_apps
from django.test import Client

import pytest

from sessionops.exceptions import ConflictError, ValidationError
from sessionops.models import Class, Program, SchoolClass
from sessionops.services.catalog.rules import assert_class_open_for_enrolment, validate_next_class
from sessionops.services.catalog.write import update_class
from sessionops.services.structure.queries import add_class_to_school
from sessionops.tests.exports.factories import (
    auth_headers,
    make_school,
    make_school_class,
    make_user,
    school_year,
)

seed_migration = importlib.import_module("sessionops.migrations.0033_seed_class_catalog")


@pytest.fixture
def catalog(db):
    """Program + 5th–8th, seeded exactly as migration 0033 does."""
    program, _ = Program.objects.get_or_create(
        program_id=1, defaults={"program_name": "Foundation Program", "is_active": True}
    )
    for code in ("5", "6", "7", "8"):
        Class.objects.get_or_create(
            class_code=code, defaults={"class_name": f"{code}th", "program_id": program}
        )
    seed_migration.seed(django_apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))
    return {c.class_code: c for c in Class.objects.all()}


@pytest.fixture
def admin(db):
    return make_user("Function Lead")


@pytest.fixture
def client():
    return Client()


URL = "/api/admin/classes/"


# ── Seed migration ─────────────────────────────────────────────────────────────


def test_seed_sets_order_next_class_and_closes_8th(catalog):
    c = catalog
    assert [(k, c[k].sequence) for k in "5678"] == [
        ("5", 5),
        ("6", 6),
        ("7", 7),
        ("8", 8),
    ]
    assert c["5"].next_class_id == c["6"]
    assert c["6"].next_class_id == c["7"]
    assert c["7"].next_class_id == c["8"]
    assert c["8"].next_class_id is None
    assert [c[k].open_for_enrolment for k in "5678"] == [True, True, True, False]


def test_unseed_clears_fields(catalog):
    seed_migration.unseed(django_apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))
    assert not Class.objects.exclude(sequence=0).exists()
    assert not Class.objects.filter(next_class_id__isnull=False).exists()


# ── Rules ──────────────────────────────────────────────────────────────────────


def test_open_class_passes_closed_class_raises(catalog):
    assert_class_open_for_enrolment(catalog["7"])
    with pytest.raises(ValidationError, match="cannot be assigned directly"):
        assert_class_open_for_enrolment(catalog["8"])
    assert_class_open_for_enrolment(catalog["8"], allow_prior=True)


def test_next_class_rejects_self_inactive_and_cycles(catalog):
    c = catalog
    with pytest.raises(ValidationError, match="own next class"):
        validate_next_class(c["7"], c["7"])
    Class.objects.filter(pk=c["6"].pk).update(is_active=False)
    c["6"].refresh_from_db()
    with pytest.raises(ValidationError, match="inactive"):
        validate_next_class(c["8"], c["6"])
    with pytest.raises(ValidationError, match="cycle"):
        validate_next_class(c["7"], c["5"])  # 5 → 6 → 7 already


def test_next_class_none_is_allowed(catalog):
    validate_next_class(catalog["8"], None)


# ── Enrolment switch is data-driven ────────────────────────────────────────────


def test_add_closed_class_to_school_rejected_then_allowed_when_opened(catalog, admin):
    partner, _ = make_school()
    school_year(partner.partner_id, admin)
    with pytest.raises(ValidationError):
        add_class_to_school(partner.partner_id, catalog["8"].class_id, admin)

    Class.objects.filter(pk=catalog["8"].pk).update(open_for_enrolment=True)

    sc = add_class_to_school(partner.partner_id, catalog["8"].class_id, admin)
    assert sc.class_id_id == catalog["8"].class_id


def test_closing_a_class_blocks_it(catalog, admin):
    partner, _ = make_school()
    school_year(partner.partner_id, admin)
    Class.objects.filter(pk=catalog["5"].pk).update(open_for_enrolment=False)

    with pytest.raises(ValidationError):
        add_class_to_school(partner.partner_id, catalog["5"].class_id, admin)


# ── Update / deactivate guards ─────────────────────────────────────────────────


def _patch(**kw):
    from sessionops.schemas.catalog import AdminClassPatchIn

    return AdminClassPatchIn(**kw)


def test_deactivate_blocked_while_in_use(catalog, admin):
    partner, _ = make_school()
    make_school_class(partner.partner_id, admin, "6")  # uses catalog 6th

    with pytest.raises(ConflictError, match="used by"):
        update_class(catalog["6"].class_id, _patch(is_active=False), admin)


def test_deactivate_blocked_while_another_class_points_to_it(catalog, admin):
    with pytest.raises(ConflictError, match="next class of 7th"):
        update_class(catalog["8"].class_id, _patch(is_active=False), admin)


def test_deactivate_allowed_when_unused_and_unreferenced(catalog, admin):
    update_class(catalog["7"].class_id, _patch(next_class_id=None), admin)
    cls = update_class(catalog["8"].class_id, _patch(is_active=False), admin)
    assert cls.is_active is False


# ── Admin API ──────────────────────────────────────────────────────────────────


def test_api_list_ordered_by_sequence_with_usage(client, catalog, admin):
    partner, _ = make_school()
    make_school_class(partner.partner_id, admin, "5")
    Class.objects.create(
        class_code="10",
        class_name="10th",
        sequence=10,
        program_id=catalog["5"].program_id,
    )

    body = client.get(URL, **auth_headers(admin)).json()

    assert [c["class_code"] for c in body] == [
        "5",
        "6",
        "7",
        "8",
        "10",
    ]  # 10 after 8, not before 5
    row5 = body[0]
    assert (
        row5["next_class_name"],
        row5["in_use_count"],
        row5["open_for_enrolment"],
    ) == (
        "6th",
        1,
        True,
    )


def test_api_create_9th_and_point_8th_to_it(client, catalog, admin):
    resp = client.post(
        URL,
        {
            "class_code": "9",
            "class_name": "9th",
            "sequence": 9,
            "open_for_enrolment": False,
        },
        content_type="application/json",
        **auth_headers(admin),
    )
    assert resp.status_code == 201, resp.content
    nine = resp.json()

    resp = client.patch(
        f"{URL}{catalog['8'].class_id}/",
        {"next_class_id": nine["class_id"]},
        content_type="application/json",
        **auth_headers(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["next_class_name"] == "9th"


def test_api_duplicate_code_is_409(client, catalog, admin):
    resp = client.post(
        URL,
        {"class_code": "5", "class_name": "5th again", "sequence": 50},
        content_type="application/json",
        **auth_headers(admin),
    )
    assert resp.status_code == 409


def test_api_cycle_is_400(client, catalog, admin):
    resp = client.patch(
        f"{URL}{catalog['7'].class_id}/",
        {"next_class_id": catalog["5"].class_id},
        content_type="application/json",
        **auth_headers(admin),
    )
    assert resp.status_code == 400


def test_api_toggle_open_for_enrolment(client, catalog, admin):
    resp = client.patch(
        f"{URL}{catalog['8'].class_id}/",
        {"open_for_enrolment": True},
        content_type="application/json",
        **auth_headers(admin),
    )
    assert resp.json()["open_for_enrolment"] is True


@pytest.mark.parametrize("role", ["CO Full Time", "CHO", "CXO"])
def test_api_non_admin_forbidden(client, catalog, role):
    user = make_user(role)
    assert client.get(URL, **auth_headers(user)).status_code == 403
    resp = client.post(
        URL,
        {"class_code": "9", "class_name": "9th", "sequence": 9},
        content_type="application/json",
        **auth_headers(user),
    )
    assert resp.status_code == 403


# ── Public catalog ─────────────────────────────────────────────────────────────


def test_public_catalog_lists_open_active_classes_in_order(client, catalog):
    Class.objects.filter(pk=catalog["6"].pk).update(is_active=False)

    codes = [c["class_code"] for c in client.get("/api/classes/").json()]

    assert codes == ["5", "7"]  # 6 inactive, 8 closed


def test_school_class_list_ordered_by_sequence(catalog, admin):
    from sessionops.services.structure.queries import list_classes_for_school

    partner, _ = make_school()
    ten = Class.objects.create(
        class_code="10",
        class_name="10th",
        sequence=10,
        program_id=catalog["5"].program_id,
    )
    for code in ("10", "5"):
        make_school_class(partner.partner_id, admin, code)
    assert ten.pk
    names = [sc.class_id.class_name for sc in list_classes_for_school(partner.partner_id)]
    assert names == ["5th", "10th"]
    assert SchoolClass.objects.count() == 2


# ── Order is derived from the next-class chain (no admin input) ────────────────


def _codes_in_order():
    return list(
        Class.objects.filter(removed=False)
        .order_by("sequence")
        .values_list("class_code", flat=True)
    )


def test_compute_order_follows_chain_then_unlinked_classes_by_code():
    from sessionops.services.catalog.order import compute_order

    def c(pk, code, nxt=None):
        return SimpleNamespace(pk=pk, class_code=code, next_class_id_id=nxt)

    # 8 → 9 is listed by chain position even though "10" (unlinked) sorts by code
    classes = [c(4, "8", 5), c(1, "5", 2), c(6, "10"), c(2, "6", 3), c(3, "7", 4), c(5, "9")]
    assert [x.class_code for x in compute_order(classes)] == ["5", "6", "7", "8", "9", "10"]

    # Branches (5A and 5B both → 6) stay inside one chain; a later root (4 → 5A) leads it.
    classes = [c(1, "5A", 3), c(2, "5B", 3), c(3, "6"), c(4, "4", 1)]
    assert [x.class_code for x in compute_order(classes)] == ["4", "5A", "5B", "6"]


def test_create_ignores_typed_order_and_places_class_by_chain(client, catalog, admin):
    resp = client.post(
        URL,
        {
            "class_code": "4",
            "class_name": "4th",
            "sequence": 99,
            "next_class_id": catalog["5"].class_id,
        },
        content_type="application/json",
        **auth_headers(admin),
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["sequence"] == 1
    assert _codes_in_order() == ["4", "5", "6", "7", "8"]


def test_changing_next_class_reorders(client, catalog, admin):
    nine = client.post(
        URL,
        {"class_code": "9", "class_name": "9th"},
        content_type="application/json",
        **auth_headers(admin),
    ).json()
    eleven = client.post(
        URL,
        {"class_code": "11", "class_name": "11th"},
        content_type="application/json",
        **auth_headers(admin),
    ).json()
    # Unlinked classes come after the 5→8 chain, by code.
    assert _codes_in_order() == ["5", "6", "7", "8", "9", "11"]

    # Linking 8 → 11 puts 11 inside the chain, ahead of the unlinked 9.
    client.patch(
        f"{URL}{catalog['8'].class_id}/",
        {"next_class_id": eleven["class_id"]},
        content_type="application/json",
        **auth_headers(admin),
    )
    assert _codes_in_order() == ["5", "6", "7", "8", "11", "9"]
    assert nine["class_id"]
