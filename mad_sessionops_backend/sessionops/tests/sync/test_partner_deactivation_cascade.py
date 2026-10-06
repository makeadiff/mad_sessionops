"""
F-M4-9: Partner deactivation cascade tests.

Structural precedent: test_cascade_flows.py (F-M8a-4's worknode cascade tests) —
build the full FK chain down to the leaf table, assert soft-delete flags after
the call. cascade_deactivate_school() is tested directly here; the trigger
condition inside bulk_upsert_partners is tested separately alongside the
existing sync tests (test_trigger.py / test_incremental_sync.py).
"""

from datetime import date, time

import pytest

from sessionops.models import (
    AcademicYear,
    BatchChild,
    Child,
    ChildClass,
    ChildClassSection,
    ChildProgram,
    ChildRemovalLog,
    ChildSubject,
    Class,
    ClassSection,
    ClassSectionSubject,
    Partner,
    Program,
    SchoolAcademicYear,
    SchoolClass,
    SchoolHoliday,
    SchoolSessionDetails,
    SchoolVolunteer,
    Slot,
    SlotClassSection,
    SlotClassSectionVolunteer,
    Subject,
    User,
)
from sessionops.services.sync.partner_deactivation import (
    CHILD_REMOVAL_OTHER_DETAILS,
    CHILD_REMOVAL_REASON,
    SYSTEM_SYNC_CO_ID,
    cascade_deactivate_school,
)

# ── ID generators ──────────────────────────────────────────────────────────────

_UID = iter(range(9_000_000, 9_200_000))
_SID = iter(range(70_000, 80_000))
_CHID = iter(range(1, 100_000))


# ── Helpers ────────────────────────────────────────────────────────────────────


def _admin() -> User:
    uid = next(_UID)
    return User.objects.create(
        user_id=uid,
        user_login=f"admin{uid}@pdcascade.test",
        user_display_name=f"Admin {uid}",
        email=f"admin{uid}@pdcascade.test",
        user_role="Project Lead",
        is_active=True,
    )


def _volunteer() -> User:
    uid = next(_UID)
    return User.objects.create(
        user_id=uid,
        user_login=f"vol{uid}@pdcascade.test",
        user_display_name=f"Volunteer {uid}",
        email=f"vol{uid}@pdcascade.test",
        user_role="Youth",
        is_active=True,
    )


def _school(admin: User, **kwargs) -> int:
    sid = next(_SID)
    defaults = dict(
        partner_id=sid,
        partner_name=f"School {sid}",
        co_id=admin.user_id,
        converted=True,
        crm_partner_removed=False,
        is_active=True,
    )
    defaults.update(kwargs)
    Partner.objects.create(**defaults)
    return sid


def _say(school_id: int, admin: User) -> SchoolAcademicYear:
    year, _ = AcademicYear.objects.get_or_create(
        label="2026-2027",
        defaults={"is_active": True, "created_by": admin},
    )
    say, _ = SchoolAcademicYear.objects.get_or_create(
        school_id=school_id,
        academic_year_id=year,
        defaults={"created_by": admin},
    )
    return say


def _school_class(school_id: int, admin: User) -> SchoolClass:
    say = _say(school_id, admin)
    program, _ = Program.objects.get_or_create(program_name="Foundation Program")
    cls, _ = Class.objects.get_or_create(
        class_code="5C",
        defaults={"class_name": "5th", "program_id": program, "is_active": True},
    )
    return SchoolClass.objects.create(
        school_id=school_id,
        school_academic_year_id=say,
        class_id_id=cls.class_id,
        created_by=admin,
    )


def _class_section(school_class: SchoolClass, school_id: int, admin: User) -> ClassSection:
    return ClassSection.objects.create(
        school_class_id=school_class,
        school_id=school_id,
        section_code="A",
        section_name=f"5th - A - {school_id}",
        is_active=True,
        created_by=admin,
    )


def _class_section_subject(section: ClassSection, admin: User) -> ClassSectionSubject:
    program, _ = Program.objects.get_or_create(program_name="Foundation Program")
    subj, _ = Subject.objects.get_or_create(
        subject_name="Foundation Day 1",
        defaults={"program_id": program},
    )
    return ClassSectionSubject.objects.create(
        class_section_id=section,
        subject_id=subj,
        is_active=True,
        created_by=admin,
    )


def _slot(school_id: int, admin: User) -> Slot:
    say = _say(school_id, admin)
    return Slot.objects.create(
        school_id=school_id,
        school_academic_year_id=say,
        slot_name="Monday 09:00",
        day_of_week="monday",
        start_time=time(9, 0),
        end_time=time(10, 0),
        recurring=True,
        is_active=True,
        created_by=admin,
    )


def _slot_class_section(slot: Slot, css: ClassSectionSubject, admin: User) -> SlotClassSection:
    return SlotClassSection.objects.create(
        slot_id=slot,
        class_section_id=css.class_section_id,
        class_section_subject_id=css,
        is_active=True,
        created_by=admin,
    )


def _slot_class_section_volunteer(
    scs: SlotClassSection, volunteer: User, admin: User
) -> SlotClassSectionVolunteer:
    return SlotClassSectionVolunteer.objects.create(
        slot_class_section_id=scs,
        volunteer_id=volunteer,
        is_active=True,
        created_by=admin,
    )


def _school_volunteer(school_id: int, volunteer: User, admin: User) -> SchoolVolunteer:
    return SchoolVolunteer.objects.create(
        school_id=school_id,
        volunteer_id=volunteer,
        is_active=True,
        created_by=admin,
    )


def _child(school_id: int, admin: User) -> Child:
    cid = next(_CHID)
    return Child.objects.create(
        child_id=cid,
        school_id=school_id,
        first_name=f"Child{cid}",
        last_name="Test",
        gender="other",
        is_active=True,
        created_by=admin,
    )


def _child_class_section(child: Child, section: ClassSection, admin: User) -> ChildClassSection:
    return ChildClassSection.objects.create(
        child_id=child,
        class_section_id=section,
        is_active=True,
        created_by=admin,
    )


def _child_class(child: Child, school_class: SchoolClass, admin: User) -> ChildClass:
    return ChildClass.objects.create(
        child_id=child,
        school_class_id=school_class,
        is_active=True,
        created_by=admin,
    )


def _session_details(school_id: int, admin: User) -> SchoolSessionDetails:
    say = _say(school_id, admin)
    return SchoolSessionDetails.objects.create(
        school_id=school_id,
        school_academic_year=say,
        start_date=date(2026, 6, 1),
        end_date=date(2027, 4, 30),
        is_active=True,
        created_by=admin,
    )


def _holiday(school_id: int, admin: User, **kwargs) -> SchoolHoliday:
    defaults = dict(
        school_id=school_id,
        holiday_reason="holidays",
        start_date=date(2026, 8, 15),
        end_date=date(2026, 8, 15),
        is_active=True,
        created_by=admin,
    )
    defaults.update(kwargs)
    return SchoolHoliday.objects.create(**defaults)


def _build_full_school(admin: User) -> dict:
    """
    Build one active school with a full FK chain across all 17 cascade tables:
    slot layer (slot -> slot_class_section -> slot_class_section_volunteer),
    school_volunteer, a child with child_class_section + child_class, and the
    structural layer (class_section, school_class, school_academic_year,
    school_session_details, school_holiday).
    """
    school_id = _school(admin)
    volunteer = _volunteer()

    school_class = _school_class(school_id, admin)
    section = _class_section(school_class, school_id, admin)
    css = _class_section_subject(section, admin)

    slot = _slot(school_id, admin)
    scs = _slot_class_section(slot, css, admin)
    scsv = _slot_class_section_volunteer(scs, volunteer, admin)

    sv = _school_volunteer(school_id, volunteer, admin)

    child = _child(school_id, admin)
    ccs = _child_class_section(child, section, admin)
    cc = _child_class(child, school_class, admin)
    batch_child = BatchChild.objects.create(
        school_academic_year_id=_say(school_id, admin),
        child_id=child,
        school_id=school_id,
        created_by=admin,
    )
    program, _ = Program.objects.get_or_create(program_name="Foundation Program")
    child_program = ChildProgram.objects.create(
        program_id=program, child_id=child, created_by=admin
    )
    child_subject = ChildSubject.objects.create(
        child_id=child, class_section_subject_id=css, created_by=admin
    )

    session = _session_details(school_id, admin)
    holiday = _holiday(school_id, admin)

    return {
        "school_id": school_id,
        "volunteer": volunteer,
        "school_class": school_class,
        "section": section,
        "css": css,
        "slot": slot,
        "scs": scs,
        "scsv": scsv,
        "sv": sv,
        "child": child,
        "ccs": ccs,
        "cc": cc,
        "batch_child": batch_child,
        "child_program": child_program,
        "child_subject": child_subject,
        "session": session,
        "holiday": holiday,
    }


def _assert_inactive(model, **filters):
    obj = model.objects.get(**filters)
    assert obj.is_active is False
    if hasattr(obj, "removed"):
        assert obj.removed is True
    assert obj.deleted_at is not None
    return obj


# ── Per-table deactivation ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_cascade_deactivates_all_active_slot_class_section_volunteers():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    _assert_inactive(SlotClassSectionVolunteer, pk=built["scsv"].pk)


@pytest.mark.django_db
def test_cascade_deactivates_all_active_slot_class_sections():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    _assert_inactive(SlotClassSection, pk=built["scs"].pk)


@pytest.mark.django_db
def test_cascade_deactivates_all_active_slots():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    _assert_inactive(Slot, pk=built["slot"].pk)


@pytest.mark.django_db
def test_cascade_deactivates_all_active_class_section_subjects():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    _assert_inactive(ClassSectionSubject, pk=built["css"].pk)


@pytest.mark.django_db
def test_cascade_deactivates_all_active_school_volunteers():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    _assert_inactive(SchoolVolunteer, pk=built["sv"].pk)


@pytest.mark.django_db
def test_cascade_deactivates_all_active_child_class_sections():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    _assert_inactive(ChildClassSection, pk=built["ccs"].pk)


@pytest.mark.django_db
def test_cascade_creates_removal_log_per_active_child_with_reason_other_and_fixed_details():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    log = ChildRemovalLog.objects.get(child_id=built["child"])
    assert log.removed_reason == CHILD_REMOVAL_REASON == "other"
    assert log.other_details == CHILD_REMOVAL_OTHER_DETAILS == "School dropped from CRM"
    assert log.co_id == SYSTEM_SYNC_CO_ID == 485003
    assert log.school_id == built["school_id"]


@pytest.mark.django_db
def test_cascade_deactivates_all_active_children():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    child = Child.objects.get(pk=built["child"].pk)
    assert child.is_active is False
    assert child.removed is True


@pytest.mark.django_db
def test_cascade_deactivates_all_active_child_classes():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    _assert_inactive(ChildClass, pk=built["cc"].pk)


@pytest.mark.django_db
def test_cascade_deactivates_child_batch_program_and_subject_links():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    _assert_inactive(BatchChild, pk=built["batch_child"].pk)
    _assert_inactive(ChildProgram, pk=built["child_program"].pk)
    _assert_inactive(ChildSubject, pk=built["child_subject"].pk)


@pytest.mark.django_db
def test_cascade_deactivates_all_active_class_sections():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    _assert_inactive(ClassSection, pk=built["section"].pk)


@pytest.mark.django_db
def test_cascade_deactivates_all_active_school_classes():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    _assert_inactive(SchoolClass, pk=built["school_class"].pk)


@pytest.mark.django_db
def test_cascade_deactivates_all_active_school_academic_years():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    say = SchoolAcademicYear.objects.get(school_id=built["school_id"])
    assert say.is_active is False
    assert say.removed is True


@pytest.mark.django_db
def test_cascade_deactivates_all_active_school_session_details():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    _assert_inactive(SchoolSessionDetails, pk=built["session"].pk)


@pytest.mark.django_db
def test_cascade_deactivates_all_active_school_holidays_including_future_dated():
    admin = _admin()
    built = _build_full_school(admin)
    future_holiday = _holiday(
        built["school_id"],
        admin,
        start_date=date(2027, 3, 1),
        end_date=date(2027, 3, 1),
    )

    cascade_deactivate_school(built["school_id"])

    _assert_inactive(SchoolHoliday, pk=built["holiday"].pk)
    _assert_inactive(SchoolHoliday, pk=future_holiday.pk)


@pytest.mark.django_db
def test_cascade_sets_partner_is_active_false():
    admin = _admin()
    built = _build_full_school(admin)

    cascade_deactivate_school(built["school_id"])

    partner = Partner.all_objects.get(partner_id=built["school_id"])
    assert partner.is_active is False
    assert partner.deleted_at is not None


# ── Isolation, idempotency, counts, rollback ────────────────────────────────────


@pytest.mark.django_db
def test_cascade_does_not_touch_records_at_a_different_school_id():
    admin = _admin()
    target = _build_full_school(admin)
    other = _build_full_school(admin)

    cascade_deactivate_school(target["school_id"])

    other_partner = Partner.all_objects.get(partner_id=other["school_id"])
    assert other_partner.is_active is True
    other_slot = Slot.objects.get(pk=other["slot"].pk)
    assert other_slot.is_active is True
    other_child = Child.objects.get(pk=other["child"].pk)
    assert other_child.is_active is True
    assert not ChildRemovalLog.objects.filter(child_id=other["child"]).exists()


@pytest.mark.django_db
def test_cascade_is_a_noop_when_rerun_against_an_already_cascaded_school():
    admin = _admin()
    built = _build_full_school(admin)

    first = cascade_deactivate_school(built["school_id"])
    assert sum(first.values()) > 0

    second = cascade_deactivate_school(built["school_id"])
    assert all(v == 0 for v in second.values())

    # No duplicate removal log rows from the second call.
    assert ChildRemovalLog.objects.filter(child_id=built["child"]).count() == 1


@pytest.mark.django_db
def test_cascade_returns_accurate_counts_dict():
    admin = _admin()
    built = _build_full_school(admin)

    counts = cascade_deactivate_school(built["school_id"])

    assert counts["slot_class_section_volunteer"] == 1
    assert counts["slot_class_section"] == 1
    assert counts["slot"] == 1
    assert counts["class_section_subject"] == 1
    assert counts["school_volunteer"] == 1
    assert counts["child_class_section"] == 1
    assert counts["child_removal_log"] == 1
    assert counts["child"] == 1
    assert counts["child_class"] == 1
    assert counts["batch_child"] == 1
    assert counts["child_program"] == 1
    assert counts["child_subject"] == 1
    assert counts["class_section"] == 1
    assert counts["school_class"] == 1
    assert counts["school_academic_year"] == 1
    assert counts["school_session_details"] == 1
    assert counts["school_holiday"] == 1
    assert counts["partner"] == 1


@pytest.mark.django_db
def test_cascade_rolls_back_all_steps_if_one_step_raises(monkeypatch):
    admin = _admin()
    built = _build_full_school(admin)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated mid-cascade failure")

    monkeypatch.setattr(
        "sessionops.services.sync.partner_deactivation.SchoolHoliday.objects.filter",
        _boom,
    )

    with pytest.raises(RuntimeError):
        cascade_deactivate_school(built["school_id"])

    # Steps that ran before the failure must have rolled back too.
    slot = Slot.objects.get(pk=built["slot"].pk)
    assert slot.is_active is True
    child = Child.objects.get(pk=built["child"].pk)
    assert child.is_active is True
    assert not ChildRemovalLog.objects.filter(child_id=built["child"]).exists()
    partner = Partner.all_objects.get(partner_id=built["school_id"])
    assert partner.is_active is True
