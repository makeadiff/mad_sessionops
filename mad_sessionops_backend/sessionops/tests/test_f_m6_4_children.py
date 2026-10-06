"""
Tests for F-M6-4: Child enrollment decoupling + ChildOut/list_children contract.
"""

import json

from django.test import Client

import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from sessionops.exceptions import ValidationError
from sessionops.models import (
    AcademicYear,
    Child,
    ChildClass,
    Class,
    ClassSection,
    Partner,
    Program,
    SchoolAcademicYear,
    SchoolClass,
    User,
)
from sessionops.schemas.children import ChildEditIn, ChildEnrollIn
from sessionops.services.children.edit import edit_child
from sessionops.services.children.enroll import enroll_child
from sessionops.services.children.queries import list_children

# ── Helpers ────────────────────────────────────────────────────────────────────

_UID = iter(range(10_000_000, 10_100_000))
_SID = iter(range(98_000, 99_000))


def _make_user(role: str = "Function Lead") -> User:
    uid = next(_UID)
    return User.objects.create(
        user_login=f"user{uid}@test.com",
        user_display_name=f"User {uid}",
        email=f"user{uid}@test.com",
        user_role=role,
        is_active=True,
    )


def _make_partner(partner_id: int) -> Partner:
    return Partner.objects.create(
        partner_id=partner_id,
        partner_name=f"School {partner_id}",
        converted=True,
        is_active=True,
    )


def _make_school_class(school_id: int, user: User, class_code: str = "5") -> SchoolClass:
    program, _ = Program.objects.get_or_create(program_name="Foundation Program")
    cls, _ = Class.objects.get_or_create(
        class_code=class_code,
        defaults={
            "class_name": f"{class_code}th",
            "program_id": program,
            "is_active": True,
            "open_for_enrolment": class_code
            != "8",  # 8th is closed for new enrolment in the seeded catalog (F-M10-1)
        },
    )
    year, _ = AcademicYear.objects.get_or_create(
        label="2026-2027",
        defaults={"is_active": True, "created_by": user},
    )
    say, _ = SchoolAcademicYear.objects.get_or_create(
        school_id=school_id,
        academic_year_id=year,
        defaults={"created_by": user},
    )
    return SchoolClass.objects.create(
        school_id=school_id,
        school_academic_year_id=say,
        class_id_id=cls.class_id,
        created_by=user,
    )


def _make_bucket(school_id: int, user: User, name: str = "Bucket") -> ClassSection:
    return ClassSection.objects.create(
        school_id=school_id,
        section_name=name.lower().replace(" ", "_"),
        section_display_name=name,
        created_by=user,
    )


def _issue_token(user: User) -> str:
    r = RefreshToken()
    r["user_id"] = user.user_id
    r["email"] = user.email
    r["role"] = user.user_role
    r.access_token["user_id"] = user.user_id
    r.access_token["email"] = user.email
    r.access_token["role"] = user.user_role
    return str(r.access_token)


def _headers(user: User) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {_issue_token(user)}"}


@pytest.fixture
def client():
    return Client()


# ── enroll_child: decoupled bucket ─────────────────────────────────────────────


@pytest.mark.django_db
class TestEnrollDecoupled:
    def test_enroll_with_class_only_no_bucket(self):
        user = _make_user()
        _make_partner(600)
        school_class = _make_school_class(600, user)

        child = enroll_child(
            600,
            ChildEnrollIn(
                first_name="Solo",
                last_name="Child",
                gender="male",
                age=9,
                school_class_id=school_class.school_class_id,
            ),
            user,
        )

        assert child._current_school_class_id == school_class.school_class_id
        assert child._current_section_id is None

    def test_enroll_with_class_and_bucket(self):
        user = _make_user()
        _make_partner(601)
        school_class = _make_school_class(601, user)
        bucket = _make_bucket(601, user)

        child = enroll_child(
            601,
            ChildEnrollIn(
                first_name="Placed",
                last_name="Child",
                gender="female",
                age=9,
                school_class_id=school_class.school_class_id,
                class_section_id=bucket.class_section_id,
            ),
            user,
        )

        assert child._current_school_class_id == school_class.school_class_id
        assert child._current_section_id == bucket.class_section_id


# ── ChildOut contract (API level) ──────────────────────────────────────────────


@pytest.mark.django_db
def test_child_out_current_section_none_when_unassigned(client):
    user = _make_user("CO Full Time")
    _make_partner(602)
    Partner.objects.filter(partner_id=602).update(co_id=user.user_id)
    school_class = _make_school_class(602, user)

    resp = client.post(
        "/api/schools/602/children/",
        data=json.dumps(
            {
                "first_name": "Unassigned",
                "last_name": "Kid",
                "gender": "male",
                "age": 8,
                "school_class_id": school_class.school_class_id,
            }
        ),
        content_type="application/json",
        **_headers(user),
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["current_section"] is None
    assert data["current_school_class"]["school_class_id"] == school_class.school_class_id


@pytest.mark.django_db
def test_child_out_current_section_populated_with_bucket(client):
    user = _make_user("CO Full Time")
    _make_partner(603)
    Partner.objects.filter(partner_id=603).update(co_id=user.user_id)
    school_class = _make_school_class(603, user)
    bucket = _make_bucket(603, user, "Care Monster")

    resp = client.post(
        "/api/schools/603/children/",
        data=json.dumps(
            {
                "first_name": "Placed",
                "last_name": "Kid",
                "gender": "female",
                "age": 8,
                "school_class_id": school_class.school_class_id,
                "class_section_id": bucket.class_section_id,
            }
        ),
        content_type="application/json",
        **_headers(user),
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["current_section"]["class_section_id"] == bucket.class_section_id
    assert data["current_section"]["section_display_name"] == "Care Monster"


# ── list_children(unassigned=True) ─────────────────────────────────────────────


@pytest.mark.django_db
class TestListChildrenUnassignedFilter:
    def test_unassigned_filter_returns_only_bucketless_children(self):
        user = _make_user()
        _make_partner(604)
        school_class = _make_school_class(604, user)
        bucket = _make_bucket(604, user)

        enroll_child(
            604,
            ChildEnrollIn(
                first_name="NoBucket",
                last_name="A",
                gender="male",
                age=8,
                school_class_id=school_class.school_class_id,
            ),
            user,
        )
        enroll_child(
            604,
            ChildEnrollIn(
                first_name="WithBucket",
                last_name="B",
                gender="male",
                age=8,
                school_class_id=school_class.school_class_id,
                class_section_id=bucket.class_section_id,
            ),
            user,
        )

        unassigned = list_children(604, unassigned=True)
        assert unassigned.count() == 1
        assert unassigned.first().first_name == "NoBucket"

    def test_unassigned_filter_takes_precedence_over_section_id(self):
        user = _make_user()
        _make_partner(605)
        school_class = _make_school_class(605, user)
        bucket = _make_bucket(605, user)

        enroll_child(
            605,
            ChildEnrollIn(
                first_name="Solo",
                last_name="A",
                gender="male",
                age=8,
                school_class_id=school_class.school_class_id,
            ),
            user,
        )

        # section_id is ignored when unassigned=True is set
        qs = list_children(605, unassigned=True, section_id=bucket.class_section_id)
        assert qs.count() == 1


# ── edit_child: explicit school_class_id ────────────────────────────────────────


@pytest.mark.django_db
class TestEditChildSchoolClassId:
    def test_edit_without_school_class_id_leaves_class_unchanged(self):
        user = _make_user()
        _make_partner(606)
        school_class = _make_school_class(606, user)
        child = enroll_child(
            606,
            ChildEnrollIn(
                first_name="Stay",
                last_name="Same",
                gender="male",
                age=8,
                school_class_id=school_class.school_class_id,
            ),
            user,
        )

        updated = edit_child(child.child_id, ChildEditIn(first_name="Renamed"), user)

        assert updated._current_school_class_id == school_class.school_class_id


# ── Class 8 blocked for direct child assignment ─────────────────────────────────


@pytest.mark.django_db
class TestBlockedClassAssignment:
    def test_enroll_into_class_8_raises_validation_error(self):
        user = _make_user()
        _make_partner(607)
        # Class 8 SchoolClass rows only exist via migration (Bubble progression),
        # never via add_class_to_school — simulate that directly.
        class_8 = _make_school_class(607, user, class_code="8")

        with pytest.raises(ValidationError):
            enroll_child(
                607,
                ChildEnrollIn(
                    first_name="New",
                    last_name="Kid",
                    gender="male",
                    age=13,
                    school_class_id=class_8.school_class_id,
                ),
                user,
            )

    def test_edit_moving_child_into_class_8_raises_validation_error(self):
        user = _make_user()
        _make_partner(608)
        class_7 = _make_school_class(608, user, class_code="7")
        class_8 = _make_school_class(608, user, class_code="8")
        child = enroll_child(
            608,
            ChildEnrollIn(
                first_name="Seventh",
                last_name="Grader",
                gender="female",
                age=12,
                school_class_id=class_7.school_class_id,
            ),
            user,
        )

        with pytest.raises(ValidationError):
            edit_child(
                child.child_id,
                ChildEditIn(school_class_id=class_8.school_class_id),
                user,
            )

        # Original class assignment must be untouched after the rejected move.
        updated = list_children(608).get(child_id=child.child_id)
        assert updated._current_school_class_id == class_7.school_class_id

    def test_edit_child_already_in_class_8_can_still_be_edited(self):
        user = _make_user()
        _make_partner(609)
        class_8 = _make_school_class(609, user, class_code="8")
        # Child already in class 8 (as if progressed in via the legacy Bubble
        # migration, not through enroll_child which now blocks it) — build the
        # rows directly, bypassing enroll_child.
        child = Child.objects.create(
            school_id=609,
            first_name="Already",
            last_name="Eighth",
            gender="male",
            age=14,
            created_by=user,
        )
        ChildClass.objects.create(
            child_id=child,
            school_class_id=class_8,
            created_by=user,
        )

        # Editing an unrelated field, without touching school_class_id, must not
        # be blocked just because the child happens to already be in class 8.
        updated = edit_child(child.child_id, ChildEditIn(first_name="Renamed"), user)
        assert updated.first_name == "Renamed"
        assert updated._current_school_class_id == class_8.school_class_id

        # Re-submitting the SAME class_id (e.g. a form that always sends the
        # current value) must also not be blocked — it's a no-op, not a move.
        updated = edit_child(
            child.child_id,
            ChildEditIn(school_class_id=class_8.school_class_id),
            user,
        )
        assert updated._current_school_class_id == class_8.school_class_id
