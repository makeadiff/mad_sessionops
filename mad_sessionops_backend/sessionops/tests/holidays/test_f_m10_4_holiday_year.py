"""F-M10-4: holidays are linked to the school-year; old-year ones drop out of view."""

import importlib
from datetime import date
from types import SimpleNamespace

from django.apps import apps as django_apps

import pytest

from sessionops.exceptions import ConflictError
from sessionops.models import AcademicYear, SchoolAcademicYear, SchoolHoliday, SchoolSessionDetails
from sessionops.services.holidays.create import create_holiday
from sessionops.services.holidays.edit import edit_holiday
from sessionops.services.holidays.queries import list_holidays
from sessionops.tests.exports.factories import active_year, make_school, make_user, school_year

backfill_migration = importlib.import_module(
    "sessionops.migrations.0036_backfill_holiday_school_year"
)
_SCHEMA_EDITOR = SimpleNamespace(connection=SimpleNamespace(alias="default"))

OCT = {
    "holiday_reason": "holidays",
    "start_date": date(2026, 10, 1),
    "end_date": date(2026, 10, 3),
}


def _session(say, admin, start=date(2026, 6, 1), end=date(2027, 5, 31)):
    return SchoolSessionDetails.objects.create(
        school_id=say.school_id,
        school_academic_year=say,
        start_date=start,
        end_date=end,
        created_by=admin,
    )


def _progress_by_hand(say, admin, label="2027-2028"):
    """What F-M10-7 does to the school-year and session: archive, then a new year."""
    SchoolAcademicYear.objects.filter(pk=say.pk).update(is_active=False)
    SchoolSessionDetails.objects.filter(school_academic_year=say).update(is_active=False)
    year, _ = AcademicYear.objects.get_or_create(
        label=label, defaults={"is_active": False, "created_by": admin}
    )
    new_say = SchoolAcademicYear.objects.create(
        school_id=say.school_id, academic_year_id=year, created_by=admin
    )
    _session(new_say, admin, date(2026, 6, 1), date(2027, 5, 31))  # same window, new year
    return new_say


@pytest.fixture
def school(db):
    admin = make_user("Function Lead")
    active_year(admin)
    partner, _ = make_school()
    say = school_year(partner.partner_id, admin)
    _session(say, admin)
    return {"admin": admin, "pid": partner.partner_id, "say": say}


def test_new_holiday_is_linked_to_active_school_year(school):
    holiday = create_holiday(school["pid"], dict(OCT), school["admin"])
    assert holiday.school_academic_year_id == school["say"]


def test_date_edit_keeps_the_link(school):
    holiday = create_holiday(school["pid"], dict(OCT), school["admin"])
    edited = edit_holiday(
        holiday.school_holiday_id,
        {"start_date": date(2026, 10, 5), "end_date": date(2026, 10, 6)},
        school["admin"],
    )
    assert edited.school_academic_year_id == school["say"]


def test_after_progression_old_holidays_are_hidden(school):
    create_holiday(school["pid"], dict(OCT), school["admin"])
    _progress_by_hand(school["say"], school["admin"])

    assert list_holidays(school["pid"]) == []
    # Not archived — just out of scope.
    assert SchoolHoliday.objects.filter(school_id=school["pid"], is_active=True).count() == 1


def test_after_progression_same_dates_do_not_conflict(school):
    create_holiday(school["pid"], dict(OCT), school["admin"])
    new_say = _progress_by_hand(school["say"], school["admin"])

    holiday = create_holiday(school["pid"], dict(OCT), school["admin"])

    assert holiday.school_academic_year_id == new_say
    assert [h.pk for h in list_holidays(school["pid"])] == [holiday.pk]


def test_overlap_within_the_year_still_rejected(school):
    create_holiday(school["pid"], dict(OCT), school["admin"])
    with pytest.raises(ConflictError):
        create_holiday(school["pid"], dict(OCT), school["admin"])


def test_legacy_null_holiday_still_visible_and_checked(school):
    SchoolHoliday.objects.create(
        school_id=school["pid"],
        holiday_reason="holidays",
        start_date=date(2026, 12, 25),
        end_date=date(2026, 12, 25),
        created_by=school["admin"],
    )

    assert len(list_holidays(school["pid"])) == 1
    with pytest.raises(ConflictError):
        create_holiday(
            school["pid"],
            {
                "holiday_reason": "holidays",
                "start_date": date(2026, 12, 25),
                "end_date": date(2026, 12, 25),
            },
            school["admin"],
        )


def test_backfill_links_holidays_and_leaves_schoolless_null(school):
    linked = SchoolHoliday.objects.create(
        school_id=school["pid"],
        holiday_reason="holidays",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 1),
        created_by=school["admin"],
    )
    other, _ = make_school()  # no school-year at all
    orphan = SchoolHoliday.objects.create(
        school_id=other.partner_id,
        holiday_reason="holidays",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 1),
        created_by=school["admin"],
    )

    backfill_migration.backfill(django_apps, _SCHEMA_EDITOR)

    linked.refresh_from_db()
    orphan.refresh_from_db()
    assert linked.school_academic_year_id == school["say"]
    assert orphan.school_academic_year_id is None
