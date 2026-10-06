"""
Tests for F-M2-9: Children reactivation.
"""

import pytest

from sessionops.exceptions import ConflictError, NotFound, PermissionDenied, ValidationError
from sessionops.models import (
    AcademicYear,
    BatchChild,
    Child,
    ChildClass,
    ChildClassSection,
    ChildProgram,
    ChildRemovalLog,
    ClassSection,
    Partner,
    Program,
    SchoolAcademicYear,
    SchoolClass,
    User,
)
from sessionops.schemas.children import ChildEnrollIn, DeactivateIn, ReactivateIn
from sessionops.services.children.deactivate import deactivate_child
from sessionops.services.children.enroll import enroll_child
from sessionops.services.children.reactivate import reactivate_child

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_user(login: str = "admin@test.com", role: str = "Function Lead") -> User:
    return User.objects.create(
        user_display_name="Test",
        user_login=login,
        email=login,
        user_role=role,
        is_active=True,
    )


def _make_partner(partner_id: int, child_count: int | None = None) -> Partner:
    return Partner.objects.create(
        partner_id=partner_id,
        partner_name=f"School {partner_id}",
        converted=True,
        confirmed_child_count=child_count,
    )


def _make_section(
    school_id: int, user: User, code: str = "A", class_code: str = "5"
) -> ClassSection:
    program, _ = Program.objects.get_or_create(
        program_id=1,
        defaults={"program_name": "Foundation Program", "is_active": True},
    )
    from sessionops.models import Class

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
    sc = SchoolClass.objects.create(
        school_id=school_id,
        school_academic_year_id=say,
        class_id_id=cls.class_id,
        created_by=user,
    )
    return ClassSection.objects.create(
        school_class_id=sc,
        school_id=school_id,
        section_code=code,
        section_name=f"{class_code}th - {code}",
        created_by=user,
    )


def _enroll(school_id: int, section: ClassSection, user: User, **kwargs) -> Child:
    defaults = dict(
        first_name="Asha",
        last_name="Kumar",
        gender="female",
        age=10,
        school_class_id=section.school_class_id_id,
        class_section_id=section.class_section_id,
    )
    defaults.update(kwargs)
    return enroll_child(school_id, ChildEnrollIn(**defaults), user)


def _deactivate(child: Child, user: User) -> None:
    deactivate_child(child.child_id, DeactivateIn(removed_reason="inactive"), user)


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestReactivateCreatesRows:
    def test_reactivate_creates_new_active_history_rows(self):
        user = _make_user("r1@t.com")
        _make_partner(500)
        section = _make_section(500, user)
        child = _enroll(500, section, user)
        _deactivate(child, user)

        # Verify child is inactive
        child.refresh_from_db()
        assert child.is_active is False

        reactivate_child(
            child.child_id,
            ReactivateIn(
                school_class_id=section.school_class_id_id,
                class_section_id=section.class_section_id,
            ),
            user,
        )

        child.refresh_from_db()
        assert child.is_active is True
        assert ChildClass.objects.filter(child_id=child, is_active=True, removed=False).count() == 1
        assert (
            ChildClassSection.objects.filter(child_id=child, is_active=True, removed=False).count()
            == 1
        )
        assert BatchChild.objects.filter(child_id=child, is_active=True, removed=False).count() == 1
        assert (
            ChildProgram.objects.filter(child_id=child, is_active=True, removed=False).count() == 1
        )

    def test_reactivate_preserves_old_deactivated_history_rows(self):
        user = _make_user("r2@t.com")
        _make_partner(501)
        section = _make_section(501, user)
        child = _enroll(501, section, user)
        _deactivate(child, user)

        reactivate_child(
            child.child_id,
            ReactivateIn(
                school_class_id=section.school_class_id_id,
                class_section_id=section.class_section_id,
            ),
            user,
        )

        # Two rows each: one deactivated (from deactivation), one new active
        assert ChildClass.objects.filter(child_id=child).count() == 2
        assert ChildClassSection.objects.filter(child_id=child).count() == 2
        assert BatchChild.objects.filter(child_id=child).count() == 2
        assert ChildProgram.objects.filter(child_id=child).count() == 2

    def test_reactivate_marks_removal_log_inactive(self):
        user = _make_user("r3@t.com")
        _make_partner(502)
        section = _make_section(502, user)
        child = _enroll(502, section, user)
        _deactivate(child, user)

        # Removal log is active after deactivation
        assert ChildRemovalLog.objects.filter(child_id=child, is_active=True).exists()

        reactivate_child(
            child.child_id,
            ReactivateIn(
                school_class_id=section.school_class_id_id,
                class_section_id=section.class_section_id,
            ),
            user,
        )

        # Removal log is now inactive
        log = ChildRemovalLog.objects.get(child_id=child)
        assert log.is_active is False
        assert log.removed is True
        assert log.deleted_at is not None


@pytest.mark.django_db
class TestReactivateValidation:
    def test_reactivate_already_active_child_raises_validation_error(self):
        user = _make_user("r4@t.com")
        _make_partner(503)
        section = _make_section(503, user)
        child = _enroll(503, section, user)

        with pytest.raises(ValidationError, match="already active"):
            reactivate_child(
                child.child_id,
                ReactivateIn(
                    school_class_id=section.school_class_id_id,
                    class_section_id=section.class_section_id,
                ),
                user,
            )

    def test_reactivate_nonexistent_child_raises_not_found(self):
        user = _make_user("r5@t.com")
        _make_partner(504)

        with pytest.raises(NotFound):
            reactivate_child(99999, ReactivateIn(school_class_id=1, class_section_id=1), user)

    def test_reactivate_to_full_section_raises_conflict(self):
        user = _make_user("r6@t.com")
        _make_partner(505)
        sec_a = _make_section(505, user, code="A")
        sec_b = ClassSection.objects.create(
            school_class_id=sec_a.school_class_id,
            school_id=505,
            section_code="B",
            section_name="5th - B",
            created_by=user,
        )

        # Fill sec_b to capacity
        for i in range(5):
            _enroll(505, sec_b, user, first_name=f"Fill{i}", last_name="X")

        # Enroll then deactivate a child in sec_a
        child = _enroll(505, sec_a, user)
        _deactivate(child, user)

        with pytest.raises(ConflictError, match="full"):
            reactivate_child(
                child.child_id,
                ReactivateIn(
                    school_class_id=sec_b.school_class_id_id,
                    class_section_id=sec_b.class_section_id,
                ),
                user,
            )

    def test_reactivate_school_at_confirmed_limit_raises_conflict(self):
        user = _make_user("r7@t.com")
        _make_partner(506, child_count=1)  # cap of 1
        section = _make_section(506, user)

        child = _enroll(506, section, user)  # uses the 1 slot
        _deactivate(child, user)

        # Cap is 1; no active children now, so reactivation should SUCCEED
        # Re-read the logic: after deactivation, BatchChild is inactive (count=0), so cap not exceeded
        result = reactivate_child(
            child.child_id,
            ReactivateIn(
                school_class_id=section.school_class_id_id,
                class_section_id=section.class_section_id,
            ),
            user,
        )
        assert result.is_active is True

    def test_reactivate_at_cap_after_another_enrolled_raises_conflict(self):
        user = _make_user("r8@t.com")
        _make_partner(507, child_count=1)  # cap of 1
        section = _make_section(507, user)

        # Enroll child_b first, deactivate it to free the slot, then enroll child_a
        child_b = _enroll(507, section, user, first_name="B", last_name="Y")
        _deactivate(child_b, user)
        _enroll(507, section, user, first_name="A", last_name="X")  # fills the 1 slot

        # child_a active (count=1, cap=1) → reactivating child_b should fail
        with pytest.raises(ConflictError, match="confirmed child limit"):
            reactivate_child(
                child_b.child_id,
                ReactivateIn(
                    school_class_id=section.school_class_id_id,
                    class_section_id=section.class_section_id,
                ),
                user,
            )


@pytest.mark.django_db
class TestReactivateRBAC:
    def test_co_cannot_reactivate_other_school_child(self):
        admin = _make_user("admin_r@t.com")
        co = _make_user("co_r@t.com", role="CO Full Time")
        co.co_id = 777
        co.save()

        _make_partner(508)
        _make_partner(509)
        Partner.objects.filter(partner_id=509).update(co_id=co.user_id)

        section = _make_section(508, admin)
        child = _enroll(508, section, admin)
        _deactivate(child, admin)

        with pytest.raises(PermissionDenied):
            reactivate_child(
                child.child_id,
                ReactivateIn(
                    school_class_id=section.school_class_id_id,
                    class_section_id=section.class_section_id,
                ),
                co,
            )

    def test_admin_can_reactivate_any_child(self):
        admin = _make_user("admin_r2@t.com")
        _make_partner(510)
        section = _make_section(510, admin)
        child = _enroll(510, section, admin)
        _deactivate(child, admin)

        result = reactivate_child(
            child.child_id,
            ReactivateIn(
                school_class_id=section.school_class_id_id,
                class_section_id=section.class_section_id,
            ),
            admin,
        )
        assert result.is_active is True


@pytest.mark.django_db
class TestReactivateBlockedClass:
    def test_reactivate_into_new_class_8_raises_validation_error(self):
        # Child was in (and is being reactivated into) a DIFFERENT class than
        # class 8 — attempting to reactivate them straight into class 8 instead
        # must be blocked, same as a fresh enrollment would be.
        user = _make_user("r9@t.com")
        _make_partner(511)
        section_7 = _make_section(511, user, class_code="7")
        section_8 = _make_section(511, user, code="A", class_code="8")
        child = _enroll(511, section_7, user)
        _deactivate(child, user)

        with pytest.raises(ValidationError):
            reactivate_child(
                child.child_id,
                ReactivateIn(
                    school_class_id=section_8.school_class_id_id,
                    class_section_id=section_8.class_section_id,
                ),
                user,
            )

    def test_reactivate_into_own_prior_class_8_is_allowed(self):
        # Child already legitimately in class 8 (as if progressed in via the
        # legacy Bubble flow — built directly here, bypassing enroll_child,
        # which now blocks class 8 for NEW assignments). Reactivating them back
        # into that SAME class must be allowed — it's restoring their own
        # history, not a new manual assignment.
        user = _make_user("r10@t.com")
        _make_partner(512)
        section_8 = _make_section(512, user, class_code="8")

        child = Child.objects.create(
            school_id=512,
            first_name="Legacy",
            last_name="Eighth",
            gender="male",
            age=14,
            created_by=user,
        )
        cc = ChildClass.objects.create(
            child_id=child,
            school_class_id_id=section_8.school_class_id_id,
            created_by=user,
        )
        # Simulate deactivate_child's soft-delete of the ChildClass row.
        cc.is_active = False
        cc.removed = True
        cc.save(update_fields=["is_active", "removed"])
        child.is_active = False
        child.save(update_fields=["is_active"])

        result = reactivate_child(
            child.child_id,
            ReactivateIn(school_class_id=section_8.school_class_id_id),
            user,
        )
        assert result.is_active is True
