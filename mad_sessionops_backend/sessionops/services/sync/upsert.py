"""
Shared upsert helpers for Hasura sync.

Used by both the legacy run_sync() and the new incremental sync.
Extracted here so incremental.py and single_user.py can import without
circular imports against sync/__init__.py.
"""

import logging
import time
from datetime import date, datetime, timezone

from django.db import IntegrityError, OperationalError
from django.db import close_old_connections as _close_old_connections
from django.db import connection, transaction

from sessionops.models import Partner, PartnerWorknode, User
from sessionops.services.sync.partner_deactivation import cascade_deactivate_school

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def close_old_connections() -> None:
    """
    Refresh a stale DB connection between batches of a long-running sync.

    Guarded on connection.in_atomic_block: this is meant for the real
    background-thread/cron path, which isn't wrapped in an outer transaction.
    Calling Django's close_old_connections() while inside one (as every
    pytest-django @pytest.mark.django_db test is, since these same functions
    are also called directly and synchronously in unit tests) can close the
    connection pytest-django's rollback-based test isolation depends on,
    surfacing as an unrelated "connection already closed" failure later in
    the same test session.
    """
    if not connection.in_atomic_block:
        _close_old_connections()


USER_UPDATE_FIELDS = [
    "user_login",
    "user_display_name",
    "email",
    "user_role",
    "worknode_id",
    "synced_at",
]

PARTNER_UPDATE_FIELDS = [
    "partner_name",
    "co_id",
    "co_name",
    "address_line_1",
    "address_line_2",
    "city",
    "city_id",
    "state",
    "state_id",
    "pincode",
    "school_type",
    "partner_affiliation_type",
    "poc_name",
    "poc_email",
    "poc_designation",
    "poc_contact",
    "mou_sign_date",
    "mou_start_date",
    "mou_end_date",
    "mou_url",
    "converted",
    "crm_partner_removed",
    "latest_conversion_stage",
    "lead_source",
    "date_of_first_contact",
    "confirmed_child_count",
    "total_child_count",
    "classes",
    "partner_created_date",
    "partner_updated_date",
    "synced_at",
    "is_active",
]

# ---------------------------------------------------------------------------
# Field parsing helpers
# ---------------------------------------------------------------------------


def parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def parse_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def to_str(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def to_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Object builders
# ---------------------------------------------------------------------------


def build_user_obj(row: dict, now: datetime) -> User | None:
    user_id = row.get("user_id")
    if not user_id:
        return None
    return User(
        user_id=user_id,
        user_login=(row.get("user_login") or "").lower().strip(),
        user_display_name=to_str(row.get("user_display_name")) or "",
        email=(row.get("email") or "").lower().strip(),
        user_role=to_str(row.get("user_role")) or "",
        worknode_id=to_int(row.get("worknode_id")),
        synced_at=now,
    )


def build_partner_obj(row: dict, now: datetime) -> Partner | None:
    partner_id = to_int(row.get("partner_id"))
    if partner_id is None:
        return None
    crm_removed = bool(row.get("crm_partner_removed", False))
    return Partner(
        partner_id=partner_id,
        partner_name=to_str(row.get("partner_name")) or "",
        co_id=to_int(row.get("co_id")),
        co_name=to_str(row.get("co_name")),
        address_line_1=to_str(row.get("address_line_1")),
        address_line_2=to_str(row.get("address_line_2")),
        city=to_str(row.get("city")),
        city_id=to_int(row.get("city_id")),
        state=to_str(row.get("state")),
        state_id=to_int(row.get("state_id")),
        pincode=to_int(row.get("pincode")),
        school_type=to_str(row.get("school_type")),
        partner_affiliation_type=to_str(row.get("partner_affiliation_type")),
        poc_name=to_str(row.get("poc_name")),
        poc_email=to_str(row.get("poc_email")),
        poc_designation=to_str(row.get("poc_designation")),
        poc_contact=to_str(row.get("poc_contact")),
        mou_sign_date=parse_date(row.get("mou_sign_date")),
        mou_start_date=parse_date(row.get("mou_start_date")),
        mou_end_date=parse_date(row.get("mou_end_date")),
        mou_url=to_str(row.get("mou_url")),
        converted=bool(row.get("converted", False)),
        crm_partner_removed=crm_removed,
        latest_conversion_stage=to_str(row.get("latest_conversion_stage")),
        lead_source=to_str(row.get("lead_source")),
        date_of_first_contact=parse_datetime(row.get("date_of_first_contact")),
        confirmed_child_count=to_int(row.get("confirmed_child_count")),
        total_child_count=to_int(row.get("total_child_count")),
        classes=to_str(row.get("classes")),
        partner_created_date=parse_datetime(row.get("partner_created_date")),
        partner_updated_date=parse_datetime(row.get("partner_updated_date")),
        synced_at=now,
        is_active=not crm_removed,
    )


# ---------------------------------------------------------------------------
# Single-row fallback (used when bulk hits a user_login collision)
# ---------------------------------------------------------------------------


def upsert_user_single(row: dict, now: datetime) -> bool:
    user_id = row.get("user_id")
    if not user_id:
        return False
    defaults = {
        "user_login": (row.get("user_login") or "").lower().strip(),
        "user_display_name": to_str(row.get("user_display_name")) or "",
        "email": (row.get("email") or "").lower().strip(),
        "user_role": to_str(row.get("user_role")) or "",
        "worknode_id": to_int(row.get("worknode_id")),
        "synced_at": now,
    }
    for attempt in range(2):
        try:
            with transaction.atomic():
                _, created = User.objects.update_or_create(user_id=user_id, defaults=defaults)
                return created
        except IntegrityError:
            user_login = defaults["user_login"]
            logger.warning(
                "upsert_user_single: user_login=%s exists under a different user_id; "
                "updating that row to user_id=%s",
                user_login,
                user_id,
            )
            with transaction.atomic():
                User.objects.filter(user_login=user_login).update(user_id=user_id, **defaults)
            return False
        except OperationalError:
            if attempt == 0:
                logger.warning("upsert_user_single: connection lost, reconnecting...")
                close_old_connections()
                time.sleep(2)
            else:
                raise
    return False


# ---------------------------------------------------------------------------
# Bulk upsert helpers
# ---------------------------------------------------------------------------


def bulk_upsert_users(batch_rows: list[dict], now: datetime) -> tuple[int, int]:
    """
    Bulk upsert users using INSERT ... ON CONFLICT DO UPDATE.
    Returns (created, updated). Falls back to row-by-row on user_login collision.
    """
    objects = [obj for row in batch_rows if (obj := build_user_obj(row, now))]
    if not objects:
        return 0, 0

    batch_ids = [o.user_id for o in objects]
    existing_ids = set(User.objects.filter(user_id__in=batch_ids).values_list("user_id", flat=True))

    try:
        User.objects.bulk_create(
            objects,
            update_conflicts=True,
            update_fields=USER_UPDATE_FIELDS,
            unique_fields=["user_id"],
        )
        created = sum(1 for o in objects if o.user_id not in existing_ids)
        updated = len(objects) - created
        return created, updated

    except IntegrityError:
        logger.warning("bulk_upsert_users: IntegrityError, falling back to row-by-row")
        created = updated = 0
        for row in batch_rows:
            if upsert_user_single(row, now):
                created += 1
            else:
                updated += 1
        return created, updated


def bulk_upsert_partners(batch_rows: list[dict], now: datetime) -> tuple[int, int]:
    """
    Bulk upsert partners using INSERT ... ON CONFLICT DO UPDATE.
    Uses all_objects manager so soft-deleted rows are found and reactivated.
    Returns (created, updated).

    F-M4-9: after the upsert, any partner that was previously active AND
    previously converted=True, and now reports converted=False (with or without
    crm_partner_removed=True), is cascade-deactivated (see
    services/sync/partner_deactivation.py) — i.e. a real converted partner
    reverting to a non-converted CRM stage, not a plain lead that was never
    converted in the first place. Requiring previous converted=True (not just
    previous is_active=True) matters: without it, a never-converted lead
    (crm_partner_removed=False, converted=False from creation) would get
    cascade-deactivated on every sync after its first, since it's already
    "previously active" and its row never stops matching removed=False/
    converted=False — nothing about it ever actually changed. Both snapshots
    must be taken before bulk_create runs, since that call overwrites them.
    """
    objects = [obj for row in batch_rows if (obj := build_partner_obj(row, now))]
    if not objects:
        return 0, 0

    batch_ids = [o.partner_id for o in objects]
    existing_ids = set(
        Partner.all_objects.filter(partner_id__in=batch_ids).values_list("partner_id", flat=True)
    )
    previously_active_ids = set(
        Partner.all_objects.filter(partner_id__in=batch_ids, is_active=True).values_list(
            "partner_id", flat=True
        )
    )
    previously_converted_ids = set(
        Partner.all_objects.filter(partner_id__in=batch_ids, converted=True).values_list(
            "partner_id", flat=True
        )
    )

    for attempt in range(2):
        try:
            # One transaction for the upsert AND its cascades. If a cascade fails,
            # the partner rows roll back too, so the next sync still sees the
            # partner as previously converted and retries the cascade — instead
            # of the new converted=False being committed and the cascade lost.
            with transaction.atomic():
                created, updated = _upsert_partners_and_cascade(
                    objects,
                    batch_rows,
                    now,
                    existing_ids,
                    previously_active_ids,
                    previously_converted_ids,
                )
            return created, updated
        except OperationalError:
            if attempt == 0:
                logger.warning("bulk_upsert_partners: connection lost, reconnecting...")
                close_old_connections()
                time.sleep(2)
            else:
                raise
    return 0, 0


def _upsert_partners_and_cascade(
    objects: list[Partner],
    batch_rows: list[dict],
    now: datetime,
    existing_ids: set[int],
    previously_active_ids: set[int],
    previously_converted_ids: set[int],
) -> tuple[int, int]:
    """Body of bulk_upsert_partners; the caller owns the transaction."""
    Partner.all_objects.bulk_create(
        objects,
        update_conflicts=True,
        update_fields=PARTNER_UPDATE_FIELDS,
        unique_fields=["partner_id"],
    )
    created = sum(1 for o in objects if o.partner_id not in existing_ids)
    updated = len(objects) - created

    for row in batch_rows:
        partner_id = to_int(row.get("partner_id"))
        if (
            partner_id is None
            or partner_id not in previously_active_ids
            or partner_id not in previously_converted_ids
        ):
            continue
        # Any converted→not-converted transition cascades, whether or not the CRM
        # also flags the school removed (dbt sets converted=False on removal).
        crm_removed = bool(row.get("crm_partner_removed", False))
        converted = bool(row.get("converted", False))
        if not converted:
            logger.warning(
                "bulk_upsert_partners: partner_id=%s now converted=False "
                "(crm_partner_removed=%s) after being previously active and "
                "converted — running F-M4-9 cascade deactivation",
                partner_id,
                crm_removed,
            )
            counts = cascade_deactivate_school(partner_id, now)
            logger.warning(
                "bulk_upsert_partners: F-M4-9 cascade DONE for partner_id=%s — %s",
                partner_id,
                counts,
            )

    return created, updated


def upsert_partner_worknode_row(row: dict, int_conv=to_int, str_conv=to_str) -> str | None:
    """
    Upsert a single PartnerWorknode row from Hasura chapter_mapping.
    Returns the partner_id string if upserted, None if skipped (missing keys).
    """
    chapter_id = row.get("chapter_id")
    worknode_id = row.get("worknode_id")
    if chapter_id is None or worknode_id is None:
        return None
    partner_id = str(chapter_id)
    PartnerWorknode.objects.update_or_create(
        partner_id=partner_id,
        defaults={
            "worknode_id": int_conv(worknode_id) or worknode_id,
            "city_name": str_conv(row.get("city_name")),
            "state": str_conv(row.get("state")),
            "co_name": str_conv(row.get("co_name")),
            "chapter_name": str_conv(row.get("chapter_name")),
            "engine": str_conv(row.get("engine")),
            "chapter_status": str_conv(row.get("chapter_status")),
            "sourcing_campaign_code": str_conv(row.get("sourcing_campaign_code")),
            "campaign_name": str_conv(row.get("campaign_name")),
            "fundraiser_id": str_conv(row.get("fundraiser_id")),
            "fundraiser_name": str_conv(row.get("fundraiser_name")),
        },
    )
    return partner_id
