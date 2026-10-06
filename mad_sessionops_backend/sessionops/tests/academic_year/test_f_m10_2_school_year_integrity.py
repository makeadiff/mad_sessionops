"""F-M10-2: exactly one active school-year per school; writes and reactivation land in it."""

import importlib
from types import SimpleNamespace

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction

import pytest

from sessionops.exceptions import ValidationError
from sessionops.models import (
    AcademicYear,
    Child,
    ChildClass,
    Class,
    Program,
    SchoolAcademicYear,
    SchoolClass,
)
from sessionops.schemas.children import ChildEnrollIn, DeactivateIn, ReactivateIn
from sessionops.services.academic_year.queries import (
    get_or_create_school_academic_year,
    get_school_academic_year,
)
from sessionops.services.children.deactivate import deactivate_child
from sessionops.services.children.enroll import enroll_child
from sessionops.services.children.reactivate import reactivate_child
from sessionops.tests.exports.factories import active_year, make_school, make_user

migration = importlib.import_module("sessionops.migrations.0034_one_active_school_year")
_SCHEMA_EDITOR = SimpleNamespace(connection=SimpleNamespace(alias="default"))


@pytest.fixture
def admin(db):
    user = make_user("Function Lead")
    active_year(user)
    return user


def _old_year(admin):
    year, _ = AcademicYear.objects.get_or_create(
        label="2025-2026", defaults={"is_active": False, "created_by": admin}
    )
    return year


def _class(code: str, open_for_enrolment: bool = True) -> Class:
    program, _ = Program.objects.get_or_create(
        program_id=1, defaults={"program_name": "Foundation Program", "is_active": True}
    )
    cls, _ = Class.objects.get_or_create(
        class_code=code,
        defaults={
            "class_name": f"{code}th",
            "program_id": program,
            "open_for_enrolment": open_for_enrolment,
        },
    )
    return cls


def _school_class(say: SchoolAcademicYear, cls: Class, admin) -> SchoolClass:
    return SchoolClass.objects.create(
        school_id=say.school_id,
        school_academic_year_id=say,
        class_id=cls,
        created_by=admin,
    )


def _enroll_payload(school_class: SchoolClass, **kw) -> ChildEnrollIn:
    data = dict(
        first_name="Asha",
        last_name="Kumar",
        gender="female",
        age=12,
        school_class_id=school_class.school_class_id,
    )
    data.update(kw)
    return ChildEnrollIn(**data)


# ── The constraint ─────────────────────────────────────────────────────────────


def test_second_active_school_year_is_rejected_by_db(admin):
    partner, _ = make_school()
    get_or_create_school_academic_year(partner.partner_id, admin)

    with pytest.raises(IntegrityError), transaction.atomic():
        SchoolAcademicYear.objects.create(
            school_id=partner.partner_id,
            academic_year_id=_old_year(admin),
            created_by=admin,
        )


def test_archived_or_removed_extra_rows_are_allowed(admin):
    partner, _ = make_school()
    get_or_create_school_academic_year(partner.partner_id, admin)

    SchoolAcademicYear.objects.create(
        school_id=partner.partner_id,
        academic_year_id=_old_year(admin),
        is_active=False,
        created_by=admin,
    )
    assert SchoolAcademicYear.objects.filter(school_id=partner.partner_id).count() == 2


def test_migration_precheck_passes_on_clean_data(admin):
    partner, _ = make_school()
    get_or_create_school_academic_year(partner.partner_id, admin)

    migration.check_no_duplicates(django_apps, _SCHEMA_EDITOR)  # no error


def test_migration_precheck_names_offending_schools():
    """The DB constraint now forbids real duplicates, so feed the check a stand-in queryset."""
    fake_apps = SimpleNamespace(
        get_model=lambda *_: SimpleNamespace(
            objects=SimpleNamespace(using=lambda _alias: _DupQS([4242, 17]))
        )
    )

    with pytest.raises(RuntimeError, match=r"\[17, 4242\]"):
        migration.check_no_duplicates(fake_apps, _SCHEMA_EDITOR)


class _DupQS:
    """Minimal queryset stand-in returning a fixed duplicate list (the real DB now forbids them)."""

    def __init__(self, ids):
        self._ids = ids

    def filter(self, **_):
        return self

    def values(self, *_):
        return self

    def annotate(self, **_):
        return self

    def values_list(self, *_, **__):
        return self._ids


# ── get_school_academic_year / get_or_create ───────────────────────────────────


def test_get_or_create_returns_existing_even_for_non_global_year(admin):
    partner, _ = make_school()
    old = SchoolAcademicYear.objects.create(
        school_id=partner.partner_id,
        academic_year_id=_old_year(admin),
        created_by=admin,
    )

    assert get_or_create_school_academic_year(partner.partner_id, admin) == old
    assert get_school_academic_year(partner.partner_id) == old


def test_get_or_create_creates_for_global_year_when_none(admin):
    partner, _ = make_school()
    assert get_school_academic_year(partner.partner_id) is None

    say = get_or_create_school_academic_year(partner.partner_id, admin)

    assert say.academic_year_id.is_active
    assert get_school_academic_year(partner.partner_id) == say


# ── Enroll ─────────────────────────────────────────────────────────────────────


def test_enroll_into_current_year_class(admin):
    partner, _ = make_school()
    say = get_or_create_school_academic_year(partner.partner_id, admin)
    sc = _school_class(say, _class("6"), admin)

    child = enroll_child(partner.partner_id, _enroll_payload(sc), admin)

    assert child.is_active


def test_enroll_into_archived_year_class_is_rejected(admin):
    partner, _ = make_school()
    archived = SchoolAcademicYear.objects.create(
        school_id=partner.partner_id,
        academic_year_id=_old_year(admin),
        is_active=False,
        created_by=admin,
    )
    get_or_create_school_academic_year(partner.partner_id, admin)
    old_class = _school_class(archived, _class("6"), admin)

    with pytest.raises(ValidationError, match="current academic year"):
        enroll_child(partner.partner_id, _enroll_payload(old_class), admin)


# ── Reactivate across a year boundary ──────────────────────────────────────────


def _progress_by_hand(partner_id, old_say, admin):
    """What F-M10-7 will do for the school-year: archive old, activate new."""
    SchoolAcademicYear.objects.filter(pk=old_say.pk).update(is_active=False)
    new_year, _ = AcademicYear.objects.get_or_create(
        label="2027-2028", defaults={"is_active": False, "created_by": admin}
    )
    return SchoolAcademicYear.objects.create(
        school_id=partner_id, academic_year_id=new_year, created_by=admin
    )


def test_reactivate_into_prior_closed_class_in_new_year(admin):
    partner, _ = make_school()
    old_say = get_or_create_school_academic_year(partner.partner_id, admin)
    eighth = _class("8", open_for_enrolment=True)  # open at enrolment time…
    child = enroll_child(
        partner.partner_id,
        _enroll_payload(_school_class(old_say, eighth, admin)),
        admin,
    )
    deactivate_child(child.child_id, DeactivateIn(removed_reason="inactive"), admin)
    Class.objects.filter(pk=eighth.pk).update(open_for_enrolment=False)  # …closed now

    new_say = _progress_by_hand(partner.partner_id, old_say, admin)
    new_eighth = _school_class(new_say, eighth, admin)

    reactivated = reactivate_child(
        child.child_id, ReactivateIn(school_class_id=new_eighth.school_class_id), admin
    )

    assert reactivated.is_active
    current = ChildClass.objects.get(child_id=child.child_id, is_active=True, removed=False)
    assert current.school_class_id == new_eighth


def test_reactivate_into_different_closed_class_still_rejected(admin):
    partner, _ = make_school()
    say = get_or_create_school_academic_year(partner.partner_id, admin)
    child = enroll_child(
        partner.partner_id,
        _enroll_payload(_school_class(say, _class("6"), admin)),
        admin,
    )
    deactivate_child(child.child_id, DeactivateIn(removed_reason="inactive"), admin)
    closed = _school_class(say, _class("8", open_for_enrolment=False), admin)

    with pytest.raises(ValidationError, match="cannot be assigned directly"):
        reactivate_child(
            child.child_id, ReactivateIn(school_class_id=closed.school_class_id), admin
        )
    assert not Child.objects.get(pk=child.pk).is_active


def test_reactivate_into_archived_year_class_rejected(admin):
    partner, _ = make_school()
    old_say = get_or_create_school_academic_year(partner.partner_id, admin)
    old_class = _school_class(old_say, _class("6"), admin)
    child = enroll_child(partner.partner_id, _enroll_payload(old_class), admin)
    deactivate_child(child.child_id, DeactivateIn(removed_reason="inactive"), admin)
    _progress_by_hand(partner.partner_id, old_say, admin)

    with pytest.raises(ValidationError, match="current academic year"):
        reactivate_child(
            child.child_id,
            ReactivateIn(school_class_id=old_class.school_class_id),
            admin,
        )
