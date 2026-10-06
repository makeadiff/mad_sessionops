"""
Tests for F-M2-4: Classes — catalog, add, list, remove.
"""

import pytest
from ninja.testing import TestClient

from sessionops.exceptions import ConflictError, NotFound, PermissionDenied, ValidationError
from sessionops.models import (
    AcademicYear,
    Child,
    ChildClass,
    Class,
    ClassSection,
    Partner,
    Program,
    User,
)
from sessionops.routes import api
from sessionops.services.structure.queries import (
    add_class_to_school,
    list_classes_for_school,
    soft_delete_school_class,
)

CLIENT = TestClient(api)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_user(login: str = "admin@test.com", role: str = "Function Lead") -> User:
    return User.objects.create(
        user_display_name="Test User",
        user_login=login,
        email=login,
        user_role=role,
        is_active=True,
    )


def _make_co_user(user_id_hint: int = 1) -> User:
    login = f"co{user_id_hint}@test.com"
    return User.objects.create(
        user_display_name="CO User",
        user_login=login,
        email=login,
        user_role="CO Full Time",
        is_active=True,
    )


def _make_partner(partner_id: int, co: User) -> Partner:
    return Partner.objects.create(
        partner_id=partner_id,
        partner_name=f"School {partner_id}",
        co_id=co.user_id,
        converted=True,
    )


def _make_active_year(user: User) -> AcademicYear:
    return AcademicYear.objects.create(label="2026-2027", is_active=True, created_by=user)


def _get_or_create_class(class_code: str = "5", class_name: str = "5th") -> Class:
    program, _ = Program.objects.get_or_create(program_name="Foundation Program")
    cls, _ = Class.objects.get_or_create(
        class_code=class_code,
        defaults={
            "class_name": class_name,
            "program_id": program,
            "is_active": True,
            "open_for_enrolment": class_code
            != "8",  # 8th is closed for new enrolment in the seeded catalog (F-M10-1)
        },
    )
    return cls


# ── Catalog tests ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCatalog:
    def test_seeded_classes_exist(self):
        # Seeded in dev DB; test DB gets fresh migration with no seed
        # So we create them here as part of setup
        program, _ = Program.objects.get_or_create(program_name="Foundation Program")
        for name, code in [("5th", "5"), ("6th", "6"), ("7th", "7"), ("8th", "8")]:
            Class.objects.get_or_create(
                class_code=code,
                defaults={
                    "class_name": name,
                    "program_id": program,
                    "open_for_enrolment": code != "8",
                },
            )
        assert Class.objects.filter(is_active=True, removed=False).count() == 4

    def test_seeded_program_exists(self):
        Program.objects.get_or_create(program_name="Foundation Program")
        assert Program.objects.filter(program_name="Foundation Program").exists()

    def test_catalog_endpoint_excludes_class_8(self):
        program, _ = Program.objects.get_or_create(program_name="Foundation Program")
        for name, code in [("5th", "5"), ("6th", "6"), ("7th", "7"), ("8th", "8")]:
            Class.objects.get_or_create(
                class_code=code,
                defaults={
                    "class_name": name,
                    "program_id": program,
                    "open_for_enrolment": code != "8",
                },
            )

        resp = CLIENT.get("/api/classes/")

        assert resp.status_code == 200
        codes = {c["class_code"] for c in resp.json()}
        assert codes == {"5", "6", "7"}


# ── Add class ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAddClass:
    def test_add_class_creates_school_class_row(self):
        admin = _make_user()
        _make_active_year(admin)
        cls = _get_or_create_class()
        school_id = 2001

        sc = add_class_to_school(school_id, cls.class_id, admin)

        assert sc.school_id == school_id
        assert sc.class_id_id == cls.class_id
        assert sc.is_active is True

    def test_add_class_creates_school_academic_year_if_missing(self):
        from sessionops.models import SchoolAcademicYear

        admin = _make_user()
        _make_active_year(admin)
        cls = _get_or_create_class()
        school_id = 2002

        assert not SchoolAcademicYear.objects.filter(school_id=school_id).exists()
        add_class_to_school(school_id, cls.class_id, admin)
        assert SchoolAcademicYear.objects.filter(school_id=school_id).exists()

    def test_add_duplicate_class_raises_conflict(self):
        admin = _make_user()
        _make_active_year(admin)
        cls = _get_or_create_class()
        school_id = 2003

        add_class_to_school(school_id, cls.class_id, admin)
        with pytest.raises(ConflictError):
            add_class_to_school(school_id, cls.class_id, admin)

    def test_add_nonexistent_class_raises_not_found(self):
        admin = _make_user()
        _make_active_year(admin)
        with pytest.raises(NotFound):
            add_class_to_school(9999, 999999, admin)

    def test_sections_count_is_zero_on_new_class(self):
        admin = _make_user()
        _make_active_year(admin)
        cls = _get_or_create_class()
        school_id = 2004

        sc = add_class_to_school(school_id, cls.class_id, admin)
        assert sc.sections_count == 0

    def test_add_class_8_directly_raises_validation_error(self):
        """Class 8 is only reachable via year-end progression from class 7,
        not a direct add — MAD's program scope is 5th-7th for now."""
        admin = _make_user()
        _make_active_year(admin)
        cls8 = _get_or_create_class("8", "8th")
        school_id = 2005

        with pytest.raises(ValidationError):
            add_class_to_school(school_id, cls8.class_id, admin)

    def test_add_class_5_6_7_still_allowed(self):
        admin = _make_user()
        _make_active_year(admin)
        school_id = 2006

        for code, name in [("5", "5th"), ("6", "6th"), ("7", "7th")]:
            cls = _get_or_create_class(code, name)
            sc = add_class_to_school(school_id, cls.class_id, admin)
            assert sc.class_id_id == cls.class_id


# ── List classes ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestListClasses:
    def test_list_returns_active_classes_only(self):
        admin = _make_user()
        _make_active_year(admin)
        cls5 = _get_or_create_class("5", "5th")
        cls6 = _get_or_create_class("6", "6th")
        school_id = 2010

        add_class_to_school(school_id, cls5.class_id, admin)
        add_class_to_school(school_id, cls6.class_id, admin)

        results = list(list_classes_for_school(school_id))
        assert len(results) == 2

    def test_list_excludes_removed_classes(self):
        admin = _make_user()
        _make_active_year(admin)
        cls = _get_or_create_class()
        school_id = 2011

        sc = add_class_to_school(school_id, cls.class_id, admin)
        soft_delete_school_class(sc.school_class_id, school_id, admin)

        results = list(list_classes_for_school(school_id))
        assert len(results) == 0

    def test_list_does_not_return_other_school_classes(self):
        admin = _make_user()
        _make_active_year(admin)
        cls = _get_or_create_class()

        add_class_to_school(2020, cls.class_id, admin)
        results = list(list_classes_for_school(9999))
        assert len(results) == 0


# ── Remove class ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestRemoveClass:
    def test_soft_delete_class_with_no_sections_succeeds(self):
        admin = _make_user()
        _make_active_year(admin)
        cls = _get_or_create_class()
        school_id = 2030

        sc = add_class_to_school(school_id, cls.class_id, admin)
        soft_delete_school_class(sc.school_class_id, school_id, admin)

        sc.refresh_from_db()
        assert sc.is_active is False
        assert sc.removed is True
        assert sc.deleted_at is not None

    def test_soft_delete_class_with_active_children_raises_conflict(self):
        """M6 decoupled classes from sections/buckets (buckets never set
        school_class_id — see M6 decision #1), so class deletion must guard
        against active children (via ChildClass), not sections."""
        admin = _make_user()
        _make_active_year(admin)
        cls = _get_or_create_class()
        school_id = 2031

        sc = add_class_to_school(school_id, cls.class_id, admin)
        child = Child.objects.create(
            school_id=school_id,
            first_name="Test",
            last_name="Child",
            gender="male",
            is_active=True,
            created_by=admin,
        )
        ChildClass.objects.create(child_id=child, school_class_id=sc, created_by=admin)

        with pytest.raises(ConflictError):
            soft_delete_school_class(sc.school_class_id, school_id, admin)

    def test_soft_delete_class_with_legacy_section_but_no_children_succeeds(self):
        """Regression guard: a legacy ClassSection still pointing at this class
        (grandfathered per M6 decision #10) must NOT block deletion on its own —
        only active children do, since sections/buckets are class-agnostic now."""
        admin = _make_user()
        _make_active_year(admin)
        cls = _get_or_create_class()
        school_id = 2032

        sc = add_class_to_school(school_id, cls.class_id, admin)
        ClassSection.objects.create(
            school_class_id=sc,
            school_id=school_id,
            section_code="A",
            section_name="5th - A",
            created_by=admin,
        )

        soft_delete_school_class(sc.school_class_id, school_id, admin)

        sc.refresh_from_db()
        assert sc.is_active is False
        assert sc.removed is True

    def test_soft_delete_nonexistent_raises_not_found(self):
        admin = _make_user()
        with pytest.raises(NotFound):
            soft_delete_school_class(999999, 1, admin)


# ── RBAC via get_school_or_403 (service layer test) ───────────────────────────


@pytest.mark.django_db
class TestRBAC:
    def test_co_can_access_own_school(self):
        co = _make_co_user()
        _make_partner(3001, co)
        admin = _make_user()
        _make_active_year(admin)
        cls = _get_or_create_class()

        # CO can add class to their own school (no exception raised)
        sc = add_class_to_school(3001, cls.class_id, co)
        assert sc.school_id == 3001

    def test_co_cannot_access_other_school(self):
        co = _make_co_user(1)
        other_co = _make_co_user(2)
        _make_partner(3002, other_co)

        from sessionops.services.rbac.scope import get_school_or_403

        with pytest.raises(PermissionDenied):
            get_school_or_403(co, 3002)
