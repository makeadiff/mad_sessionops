"""Shared test factories for M9 export tests (F-M9-4 onward).

Rows are created directly through the ORM (not via services) so each test can
set up exactly the state it needs, including soft-deleted rows.
"""

import csv
import io
from datetime import time
from itertools import count

from rest_framework_simplejwt.tokens import RefreshToken

from sessionops.models import (
    AcademicYear,
    Child,
    ChildClassSection,
    Class,
    ClassSection,
    ClassSectionSubject,
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

_UID = count(9_800_000)
_SID = count(98_000)
_WID = count(980_000)


def make_user(role: str = "Function Lead", worknode_id: int | None = None, **kw) -> User:
    uid = next(_UID)
    return User.objects.create(
        user_display_name=kw.pop("name", f"User {uid}"),
        user_login=f"m9f_{uid}@t.com",
        email=f"m9f_{uid}@t.com",
        user_role=role,
        is_active=kw.pop("is_active", True),
        worknode_id=worknode_id,
        **kw,
    )


def make_school(co_id: int = 1, **kw) -> tuple[Partner, int]:
    """Converted school with its own worknode mapping; returns (partner, worknode_id)."""
    sid = next(_SID)
    partner = Partner.objects.create(
        partner_id=sid,
        partner_name=kw.pop("name", f"School {sid}"),
        co_id=co_id,
        converted=True,
        **kw,
    )
    wid = next(_WID)
    PartnerWorknode.objects.create(partner_id=str(sid), worknode_id=wid)
    return partner, wid


def active_year(admin: User) -> AcademicYear:
    year, _ = AcademicYear.objects.get_or_create(
        label="2026-2027", defaults={"is_active": True, "created_by": admin}
    )
    return year


def school_year(school_id: int, admin: User) -> SchoolAcademicYear:
    say, _ = SchoolAcademicYear.objects.get_or_create(
        school_id=school_id,
        academic_year_id=active_year(admin),
        defaults={"created_by": admin},
    )
    return say


def _program() -> Program:
    program, _ = Program.objects.get_or_create(
        program_id=1, defaults={"program_name": "Foundation Program", "is_active": True}
    )
    return program


def make_school_class(school_id: int, admin: User, class_code: str = "5") -> SchoolClass:
    cls, _ = Class.objects.get_or_create(
        class_code=class_code,
        defaults={
            "class_name": f"{class_code}th",
            "program_id": _program(),
            "is_active": True,
        },
    )
    sc, _ = SchoolClass.objects.get_or_create(
        school_id=school_id,
        school_academic_year_id=school_year(school_id, admin),
        class_id_id=cls.class_id,
        defaults={"created_by": admin},
    )
    return sc


def make_bucket(
    school_id: int, admin: User, display: str = "Group A", class_code: str | None = "5"
) -> ClassSection:
    """A bucket (ClassSection). class_code=None makes a classless M6 bucket."""
    school_class = make_school_class(school_id, admin, class_code) if class_code else None
    n = next(_UID)
    return ClassSection.objects.create(
        school_class_id=school_class,
        school_id=school_id,
        section_code=None,
        section_name=f"group_{n}",
        section_display_name=display,
        school_academic_year_id=school_year(school_id, admin),
        created_by=admin,
    )


def make_slot(
    school_id: int,
    admin: User,
    day: str = "monday",
    start: time = time(10, 0),
    end: time = time(11, 0),
    **kw,
) -> Slot:
    return Slot.objects.create(
        school_id=school_id,
        school_academic_year_id=school_year(school_id, admin),
        slot_name=kw.pop("slot_name", f"{day.title()} {start:%H:%M}"),
        day_of_week=day,
        start_time=start,
        end_time=end,
        created_by=admin,
        **kw,
    )


def make_slot_class(
    slot: Slot, section: ClassSection, admin: User, subject: str = "English", **kw
) -> SlotClassSection:
    subj, _ = Subject.objects.get_or_create(
        subject_name=subject, defaults={"program_id": _program()}
    )
    css = ClassSectionSubject.objects.create(
        class_section_id=section, subject_id=subj, created_by=admin
    )
    return SlotClassSection.objects.create(
        slot_id=slot,
        class_section_id=section,
        class_section_subject_id=css,
        created_by=admin,
        **kw,
    )


def assign(scs: SlotClassSection, volunteer: User, admin: User, **kw) -> SlotClassSectionVolunteer:
    return SlotClassSectionVolunteer.objects.create(
        slot_class_section_id=scs, volunteer_id=volunteer, created_by=admin, **kw
    )


def place_child(section: ClassSection, admin: User, first_name: str = "Asha", **kw) -> Child:
    """Active child placed in the bucket (Child + active ChildClassSection)."""
    active = kw.pop("placement_active", True)
    child = Child.objects.create(
        school_id=section.school_id,
        first_name=first_name,
        last_name=kw.pop("last_name", "Kumar"),
        gender=kw.pop("gender", "female"),
        age=kw.pop("age", 10),
        created_by=admin,
        **kw,
    )
    ChildClassSection.objects.create(
        child_id=child,
        class_section_id=section,
        is_active=active,
        removed=not active,
        created_by=admin,
    )
    return child


def auth_headers(user: User) -> dict:
    r = RefreshToken()
    for claim, attr in (
        ("user_id", "user_id"),
        ("email", "email"),
        ("role", "user_role"),
    ):
        r[claim] = getattr(user, attr)
        r.access_token[claim] = getattr(user, attr)
    return {"HTTP_AUTHORIZATION": f"Bearer {r.access_token}"}


def parse_csv(response) -> list[list[str]]:
    body = response.content.decode("utf-8")
    assert body.startswith("﻿")
    return list(csv.reader(io.StringIO(body[1:])))
