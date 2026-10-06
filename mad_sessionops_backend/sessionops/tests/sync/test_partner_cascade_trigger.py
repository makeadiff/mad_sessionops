"""
F-M4-9: bulk_upsert_partners cascade trigger integration tests.

cascade_deactivate_school() itself (all 17 tables, idempotency, rollback) is
tested directly in test_partner_deactivation_cascade.py. These tests cover
only the trigger condition wired into bulk_upsert_partners: when it fires,
when it doesn't, and that both live sync entry points (cron incremental sync
and the manual "Sync now" trigger) go through the same code path and behave
identically.
"""

from datetime import time
from unittest.mock import patch

from django.utils import timezone

import pytest

from sessionops.models import AcademicYear, Partner, SchoolAcademicYear, Slot, SyncRun, User
from sessionops.services.sync.incremental import _sync_partners
from sessionops.services.sync.trigger import _execute_partner_sync
from sessionops.services.sync.upsert import bulk_upsert_partners

_UID = iter(range(9_500_000, 9_600_000))
_SID = iter(range(90_000, 100_000))


def _admin() -> User:
    uid = next(_UID)
    return User.objects.create(
        user_id=uid,
        user_login=f"admin{uid}@trigger.test",
        user_display_name=f"Admin {uid}",
        email=f"admin{uid}@trigger.test",
        user_role="Project Lead",
        is_active=True,
    )


def _active_partner(admin: User, **kwargs) -> int:
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


def _slot_for(school_id: int, admin: User) -> Slot:
    """A single active Slot under school_id — used as a tell for whether the
    F-M4-9 cascade ran (the plain F-M1-2 flag flip never touches Slot)."""
    year, _ = AcademicYear.objects.get_or_create(
        label="2026-2027", defaults={"is_active": True, "created_by": admin}
    )
    say, _ = SchoolAcademicYear.objects.get_or_create(
        school_id=school_id, academic_year_id=year, defaults={"created_by": admin}
    )
    return Slot.objects.create(
        school_id=school_id,
        school_academic_year_id=say,
        slot_name="Monday 09:00",
        day_of_week="monday",
        start_time=time(9, 0),
        end_time=time(10, 0),
        is_active=True,
        created_by=admin,
    )


def _hasura_row(partner_id: int, **kwargs) -> dict:
    row = {
        "partner_id": partner_id,
        "partner_name": f"School {partner_id}",
        "crm_partner_removed": False,
        "converted": False,
    }
    row.update(kwargs)
    return row


# ── Trigger condition ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_triggers_cascade_when_removed_false_converted_false_and_previously_active_and_converted():
    admin = _admin()
    sid = _active_partner(admin)  # converted=True, is_active=True
    slot = _slot_for(sid, admin)

    bulk_upsert_partners([_hasura_row(sid)], timezone.now())

    partner = Partner.all_objects.get(partner_id=sid)
    assert partner.is_active is False
    slot.refresh_from_db()
    assert slot.is_active is False  # only the cascade touches Slot


@pytest.mark.django_db
def test_skips_cascade_for_never_converted_lead_on_repeat_sync_with_unchanged_data():
    """
    Regression: a partner that has NEVER been converted (a plain lead) still
    gets created with is_active=True on its first sync (crm_partner_removed=
    False -> is_active=True, per F-M1-2 — unrelated to converted status).
    Without requiring previous converted=True, this partner would match
    "previously active + removed=False + converted=False" on every sync after
    its first, even though nothing about it ever changed, and get wrongly
    cascade-deactivated. Requiring previous converted=True prevents this.
    """
    sid = next(_SID)
    row = _hasura_row(sid)  # crm_partner_removed=False, converted=False

    bulk_upsert_partners([row], timezone.now())  # first sync: creates the lead
    partner = Partner.all_objects.get(partner_id=sid)
    assert partner.is_active is True

    bulk_upsert_partners([row], timezone.now())  # second sync: unchanged data
    partner.refresh_from_db()
    assert partner.is_active is True


@pytest.mark.django_db
def test_skips_cascade_when_partner_already_inactive():
    admin = _admin()
    sid = _active_partner(admin, is_active=False)
    slot = _slot_for(sid, admin)

    bulk_upsert_partners([_hasura_row(sid)], timezone.now())

    # Normal upsert logic (F-M1-2) sets is_active = not crm_partner_removed = True
    # here — that's expected. The cascade must NOT have fired on top of it.
    partner = Partner.all_objects.get(partner_id=sid)
    assert partner.is_active is True
    slot.refresh_from_db()
    assert slot.is_active is True


@pytest.mark.django_db
def test_skips_cascade_for_brand_new_partner_first_sync():
    sid = next(_SID)

    bulk_upsert_partners([_hasura_row(sid)], timezone.now())

    partner = Partner.all_objects.get(partner_id=sid)
    # No prior row existed, so "previously active" is false by construction —
    # normal upsert logic applies (is_active = not crm_partner_removed = True).
    assert partner.is_active is True


@pytest.mark.django_db
def test_skips_cascade_when_converted_true():
    admin = _admin()
    sid = _active_partner(admin)
    slot = _slot_for(sid, admin)

    bulk_upsert_partners([_hasura_row(sid, converted=True)], timezone.now())

    partner = Partner.all_objects.get(partner_id=sid)
    assert partner.is_active is True
    slot.refresh_from_db()
    assert slot.is_active is True


@pytest.mark.django_db
def test_triggers_cascade_when_crm_removed_true_and_converted_false():
    """dbt flips converted=False when a school is removed in the CRM — clear it all."""
    admin = _admin()
    sid = _active_partner(admin)
    slot = _slot_for(sid, admin)

    bulk_upsert_partners([_hasura_row(sid, crm_partner_removed=True)], timezone.now())

    partner = Partner.all_objects.get(partner_id=sid)
    assert partner.is_active is False
    slot.refresh_from_db()
    assert slot.is_active is False


@pytest.mark.django_db
def test_skips_cascade_when_crm_removed_true_but_still_converted():
    """Removed-but-converted isn't a real dbt state; only the F-M1-2 flag flip applies."""
    admin = _admin()
    sid = _active_partner(admin)
    slot = _slot_for(sid, admin)

    bulk_upsert_partners(
        [_hasura_row(sid, crm_partner_removed=True, converted=True)], timezone.now()
    )

    partner = Partner.all_objects.get(partner_id=sid)
    assert partner.is_active is False
    slot.refresh_from_db()
    assert slot.is_active is True


# ── Upsert and cascade commit together ───────────────────────────────────────────


@pytest.mark.django_db
def test_failed_cascade_rolls_back_the_partner_upsert_and_next_sync_retries_it():
    """
    The partner's new converted=False must not be committed without its cascade:
    otherwise the next sync sees it as never-converted and skips the cascade for
    good, leaving its slots/children active.
    """
    admin = _admin()
    sid = _active_partner(admin)
    slot = _slot_for(sid, admin)

    with patch(
        "sessionops.services.sync.upsert.cascade_deactivate_school",
        side_effect=RuntimeError("simulated cascade failure"),
    ):
        with pytest.raises(RuntimeError):
            bulk_upsert_partners([_hasura_row(sid, partner_name="Renamed")], timezone.now())

    partner = Partner.all_objects.get(partner_id=sid)
    assert partner.converted is True  # upsert rolled back with the cascade
    assert partner.partner_name == f"School {sid}"
    assert partner.is_active is True
    slot.refresh_from_db()
    assert slot.is_active is True

    # Next sync: same CRM row, cascade now succeeds.
    bulk_upsert_partners([_hasura_row(sid)], timezone.now())

    partner.refresh_from_db()
    assert partner.converted is False
    assert partner.is_active is False
    slot.refresh_from_db()
    assert slot.is_active is False


# ── Both live entry points share the same trigger ────────────────────────────────


@pytest.mark.django_db
def test_cascade_fires_from_incremental_cron_path():
    admin = _admin()
    sid = _active_partner(admin)
    slot = _slot_for(sid, admin)

    with patch(
        "sessionops.services.sync.incremental.fetch_partners_updated_after",
        return_value=[_hasura_row(sid)],
    ):
        _sync_partners(run_type=SyncRun.RUN_TYPE_AUTO, triggered_by=None)

    slot.refresh_from_db()
    assert slot.is_active is False
    partner = Partner.all_objects.get(partner_id=sid)
    assert partner.is_active is False


@pytest.mark.django_db
def test_cascade_fires_from_manual_trigger_path():
    admin = _admin()
    sid = _active_partner(admin)
    slot = _slot_for(sid, admin)

    run = SyncRun.objects.create(
        status=SyncRun.STATUS_RUNNING,
        run_type=SyncRun.RUN_TYPE_MANUAL,
        entity_type=SyncRun.ENTITY_TYPE_PARTNER,
        entity_sync_type=SyncRun.ENTITY_SYNC_TYPE_PARTNERS,
    )

    with patch(
        "sessionops.services.sync.trigger.fetch_partners_updated_after",
        return_value=[_hasura_row(sid)],
    ):
        _execute_partner_sync(run)

    slot.refresh_from_db()
    assert slot.is_active is False
    partner = Partner.all_objects.get(partner_id=sid)
    assert partner.is_active is False
    run.refresh_from_db()
    assert run.status == SyncRun.STATUS_SUCCESS
