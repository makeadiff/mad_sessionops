"""
Tests for F-M2-3: Academic Year Management.

Coverage:
  - get_active_academic_year() returns active year
  - Only-one-active-year constraint enforced
  - get_all_academic_years() returns list
  - create_academic_year() stays inactive, raises ConflictError on duplicate
  - update_academic_year() updates label, raises NotFound for missing
  - get_or_create_school_academic_year() creates + is idempotent
  - Label format validation (YYYY-YYYY)
"""

from django.db import IntegrityError

import pytest

from sessionops.exceptions import ConflictError, NotFound
from sessionops.models import AcademicYear, SchoolAcademicYear, User
from sessionops.schemas.academic_year import AcademicYearCreateIn, AcademicYearUpdateIn
from sessionops.services.academic_year.queries import (
    create_academic_year,
    get_active_academic_year,
    get_all_academic_years,
    get_or_create_school_academic_year,
    update_academic_year,
)


def _make_user(login: str = "admin@test.com", role: str = "Function Lead") -> User:
    return User.objects.create(
        user_display_name="Test User",
        user_login=login,
        email=login,
        user_role=role,
        is_active=True,
    )


def _make_active_year(user: User, label: str = "2026-2027") -> AcademicYear:
    return AcademicYear.objects.create(label=label, is_active=True, created_by=user)


@pytest.mark.django_db
class TestGetActiveAcademicYear:
    def test_returns_active_year(self):
        user = _make_user()
        _make_active_year(user)
        year = get_active_academic_year()
        assert year.label == "2026-2027"
        assert year.is_active is True

    def test_raises_not_found_when_none(self):
        with pytest.raises(NotFound):
            get_active_academic_year()

    def test_returns_removed_false_year_only(self):
        user = _make_user()
        AcademicYear.objects.create(
            label="2026-2027", is_active=True, removed=True, created_by=user
        )
        with pytest.raises(NotFound):
            get_active_academic_year()


@pytest.mark.django_db
class TestActiveYearConstraint:
    def test_only_one_active_year_constraint_enforced(self):
        user = _make_user()
        _make_active_year(user, "2026-2027")
        with pytest.raises(IntegrityError):
            AcademicYear.objects.create(label="2027-2028", is_active=True, created_by=user)

    def test_multiple_inactive_years_allowed(self):
        user = _make_user()
        AcademicYear.objects.create(label="2024-2025", is_active=False, created_by=user)
        AcademicYear.objects.create(label="2025-2026", is_active=False, created_by=user)
        assert AcademicYear.objects.filter(is_active=False).count() == 2


@pytest.mark.django_db
class TestGetAllAcademicYears:
    def test_returns_list(self):
        user = _make_user()
        _make_active_year(user, "2026-2027")
        AcademicYear.objects.create(label="2025-2026", is_active=False, created_by=user)
        years = get_all_academic_years()
        assert isinstance(years, list)
        assert len(years) == 2

    def test_excludes_removed_years(self):
        user = _make_user()
        _make_active_year(user, "2026-2027")
        AcademicYear.objects.create(
            label="2025-2026", is_active=False, removed=True, created_by=user
        )
        years = get_all_academic_years()
        assert len(years) == 1


@pytest.mark.django_db
class TestCreateAcademicYear:
    def test_create_year_stays_inactive(self):
        user = _make_user()
        payload = AcademicYearCreateIn(label="2026-2027")
        year = create_academic_year(payload, user)
        assert year.is_active is False
        assert year.label == "2026-2027"

    def test_create_duplicate_raises_conflict(self):
        user = _make_user()
        AcademicYear.objects.create(label="2026-2027", is_active=True, created_by=user)
        payload = AcademicYearCreateIn(label="2026-2027")
        with pytest.raises(ConflictError):
            create_academic_year(payload, user)

    def test_label_must_be_yyyy_yyyy_format(self):
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            AcademicYearCreateIn(label="2026")
        with pytest.raises(PydanticValidationError):
            AcademicYearCreateIn(label="2026/2027")
        with pytest.raises(PydanticValidationError):
            AcademicYearCreateIn(label="2026-2028")  # not consecutive


@pytest.mark.django_db
class TestUpdateAcademicYear:
    def test_update_label(self):
        user = _make_user()
        year = AcademicYear.objects.create(label="2025-2026", is_active=False, created_by=user)
        payload = AcademicYearUpdateIn(label="2024-2025")
        updated = update_academic_year(year.academic_year_id, payload)
        assert updated.label == "2024-2025"

    def test_update_nonexistent_raises_not_found(self):
        payload = AcademicYearUpdateIn(label="2030-2031")
        with pytest.raises(NotFound):
            update_academic_year(999999, payload)


@pytest.mark.django_db
class TestSchoolAcademicYearAutoCreate:
    def test_creates_on_first_call(self):
        user = _make_user()
        _make_active_year(user)
        school_id = 1001
        say = get_or_create_school_academic_year(school_id, user)
        assert say.school_id == school_id
        assert say.academic_year_id.label == "2026-2027"

    def test_is_idempotent(self):
        user = _make_user()
        _make_active_year(user)
        school_id = 1002
        say1 = get_or_create_school_academic_year(school_id, user)
        say2 = get_or_create_school_academic_year(school_id, user)
        assert say1.school_academic_year_id == say2.school_academic_year_id
        assert SchoolAcademicYear.objects.filter(school_id=school_id).count() == 1

    def test_reuses_existing_active_binding_when_global_year_has_rolled_over(self):
        """
        Regression: a school already active on an older AcademicYear must NOT get
        a second active SchoolAcademicYear row created just because the globally-
        active AcademicYear has since moved on. The school's existing active
        binding must be returned untouched.
        """
        user = _make_user()
        old_year = AcademicYear.objects.create(label="2025-2026", is_active=False, created_by=user)
        school_id = 1003
        existing_say = SchoolAcademicYear.objects.create(
            school_id=school_id, academic_year_id=old_year, is_active=True, created_by=user
        )
        _make_active_year(user, label="2026-2027")  # new global active year

        say = get_or_create_school_academic_year(school_id, user)

        assert say.school_academic_year_id == existing_say.school_academic_year_id
        assert say.academic_year_id_id == old_year.academic_year_id
        active_says = SchoolAcademicYear.objects.filter(
            school_id=school_id, is_active=True, removed=False
        )
        assert active_says.count() == 1


# ── Year guardrails (2026-10-02): next year only, remove unused, locked rename ──


def _year(user, label, active=False):
    return AcademicYear.objects.create(label=label, is_active=active, created_by=user)


@pytest.mark.django_db
class TestNextYearOnly:
    def test_only_the_year_after_the_latest_can_be_created(self):
        from sessionops.exceptions import ValidationError

        user = _make_user()
        _year(user, "2026-2027", active=True)
        with pytest.raises(ValidationError, match="must be 2027-2028"):
            create_academic_year(AcademicYearCreateIn(label="2028-2029"), user)
        with pytest.raises(ValidationError, match="must be 2027-2028"):
            create_academic_year(AcademicYearCreateIn(label="2025-2026"), user)
        assert (
            create_academic_year(AcademicYearCreateIn(label="2027-2028"), user).is_active is False
        )

    def test_re_adding_a_removed_year_restores_it(self):
        from sessionops.services.academic_year.queries import remove_academic_year

        user = _make_user()
        _year(user, "2026-2027", active=True)
        added = create_academic_year(AcademicYearCreateIn(label="2027-2028"), user)
        remove_academic_year(added.pk, user)

        again = create_academic_year(AcademicYearCreateIn(label="2027-2028"), user)

        assert again.pk == added.pk and again.removed is False and again.is_active is False


@pytest.mark.django_db
class TestRemoveYear:
    def test_removes_unused_inactive_year(self):
        from sessionops.services.academic_year.queries import remove_academic_year

        user = _make_user()
        _year(user, "2026-2027", active=True)
        nxt = _year(user, "2027-2028")
        assert [y.can_remove for y in get_all_academic_years()] == [True, False]

        remove_academic_year(nxt.pk, user)

        nxt.refresh_from_db()
        assert nxt.removed is True and nxt.deleted_at is not None
        assert [y.label for y in get_all_academic_years()] == ["2026-2027"]

    def test_refuses_active_year_and_year_used_by_a_school(self):
        from sessionops.services.academic_year.queries import remove_academic_year

        user = _make_user()
        active = _year(user, "2026-2027", active=True)
        old = _year(user, "2025-2026")
        SchoolAcademicYear.objects.create(
            school_id=1, academic_year_id=old, is_active=False, created_by=user
        )
        with pytest.raises(ConflictError, match="active academic year"):
            remove_academic_year(active.pk, user)
        with pytest.raises(ConflictError, match="used by 1 school"):
            remove_academic_year(old.pk, user)
        assert {y.label: y.school_count for y in get_all_academic_years()} == {
            "2026-2027": 0,
            "2025-2026": 1,
        }

    def test_api_delete_is_admin_only_and_returns_204(self, client):
        from sessionops.tests.exports.factories import auth_headers, make_user

        admin = make_user("Function Lead")
        _year(admin, "2026-2027", active=True)
        nxt = _year(admin, "2027-2028")
        url = f"/api/academic-years/admin/{nxt.pk}/"

        assert client.delete(url, **auth_headers(make_user("CO Full Time"))).status_code == 403
        assert client.delete(url, **auth_headers(admin)).status_code == 204


@pytest.mark.django_db
class TestRenameLocked:
    def test_rename_refused_once_a_school_uses_the_year(self):
        user = _make_user()
        _year(user, "2025-2026")
        year = _year(user, "2026-2027")
        SchoolAcademicYear.objects.create(school_id=1, academic_year_id=year, created_by=user)
        with pytest.raises(ConflictError, match="cannot be renamed"):
            update_academic_year(year.pk, AcademicYearUpdateIn(label="2027-2028"))

    def test_rename_must_keep_years_gap_free(self):
        from sessionops.exceptions import ValidationError

        user = _make_user()
        _year(user, "2026-2027", active=True)
        nxt = _year(user, "2027-2028")
        with pytest.raises(ValidationError, match="must be 2027-2028"):
            update_academic_year(nxt.pk, AcademicYearUpdateIn(label="2029-2030"))
