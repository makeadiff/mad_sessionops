"""
F-M1-3 / F-M3-4 RBAC scope filtering.

Scope rules:
  Function Lead / Project Lead / Project Associate / CXO → all partners (admin scope)
  CO Full Time / CO Part Time → partners where co_id == user.user_id
  CHO → partners where user.worknode_id maps to a PartnerWorknode row (F-M3-4)
  Other roles cannot log in, so they never reach this layer.

CXO is not in ADMIN_ROLES (which drives login-gate permissions) but is treated
as admin scope here — that is an explicit M1 decision, see milestone doc F-M1-3.
"""

from django.db.models import QuerySet

from sessionops.models import Partner, PartnerWorknode, User
from sessionops.schemas.auth import ScopeWarningSchema
from sessionops.services.auth.role_helpers import ADMIN_ROLES, parse_user_roles

_ADMIN_SCOPE_ROLES: frozenset[str] = ADMIN_ROLES | frozenset(["CXO"])
_CO_ROLES: frozenset[str] = frozenset(["CO Full Time", "CO Part Time"])
_CHO_ROLES: frozenset[str] = frozenset(["CHO"])


def _classify(user: User) -> str:
    """Return 'admin', 'co', 'cho', or 'none' based on the user's highest scope."""
    roles = set(parse_user_roles(user.user_role))
    if roles & _ADMIN_SCOPE_ROLES:
        return "admin"
    if roles & _CO_ROLES:
        return "co"
    if roles & _CHO_ROLES:
        return "cho"
    return "none"


def schools_visible_to(user: User) -> QuerySet:
    """Return a Partner queryset scoped to what the user may see.

    F-M10-5: schools frozen for year progression are hidden from non-admins.
    """
    qs = _schools_in_scope(user)
    if _classify(user) != "admin":
        from sessionops.services.progression.freeze import frozen_school_ids

        frozen = frozen_school_ids()
        if frozen:
            qs = qs.exclude(partner_id__in=frozen)
    return qs


def frozen_schools_in_scope_count(user: User) -> int:
    """How many of the user's in-scope schools are hidden by a progression freeze
    (0 for admins, who still see them) — drives the school-list banner (F-M10-5)."""
    if _classify(user) == "admin":
        return 0
    from sessionops.services.progression.freeze import frozen_school_ids

    frozen = frozen_school_ids()
    if not frozen:
        return 0
    return _schools_in_scope(user).filter(partner_id__in=frozen).count()


def _schools_in_scope(user: User) -> QuerySet:
    """Role scope only, ignoring the progression freeze."""
    scope = _classify(user)
    if scope == "admin":
        return Partner.objects.filter(converted=True)
    if scope == "co":
        return Partner.objects.filter(co_id=user.user_id, converted=True)
    if scope == "cho":
        if user.worknode_id is None:
            return Partner.objects.none()
        # order_by + distinct(*fields) is Postgres-only DISTINCT ON: for each
        # partner_id, keeps the row with the latest created_at, so a stale
        # duplicate sync row never shadows the current mapping.
        partner_ids = (
            PartnerWorknode.objects.filter(worknode_id=user.worknode_id)
            .exclude(partner_id__isnull=True)
            .exclude(partner_id="")
            .order_by("partner_id", "-created_at")
            .distinct("partner_id")
            .values_list("partner_id", flat=True)
        )
        if not partner_ids:
            return Partner.objects.none()
        return Partner.objects.filter(
            partner_id__in=list(partner_ids),
            is_active=True,
        )
    return Partner.objects.none()


_NO_SCHOOLS_WARNING = ScopeWarningSchema(
    code="no_worknode_mapping",
    message=(
        "You are not assigned to any schools or partner. "
        "Please contact your community organizer or admin."
    ),
)


def get_scope_warning(user: User) -> "ScopeWarningSchema | None":
    """Return the empty-scope warning for user, or None if they have visible schools."""
    if schools_visible_to(user).exists():
        return None
    return _NO_SCHOOLS_WARNING


def can_view_school(user: User, partner: Partner) -> bool:
    """Return True if the user may view this specific partner (school)."""
    scope = _classify(user)
    if scope == "admin":
        return True
    if scope == "co":
        return partner.co_id == user.user_id
    if scope == "cho":
        return schools_visible_to(user).filter(partner_id=partner.partner_id).exists()
    return False


def can_modify_school(user: User, partner: Partner) -> bool:
    """Return True if the user may write to this partner's data (M2+).

    Semantically identical to can_view_school; separate function for clarity
    at call sites where intent is write, not read.
    """
    return can_view_school(user, partner)


def get_school_or_403(user: User, school_id: int) -> Partner:
    """Return the Partner for school_id if visible to user, else raise PermissionDenied."""
    from sessionops.exceptions import NotFound, PermissionDenied

    try:
        partner = Partner.objects.get(partner_id=school_id)
    except Partner.DoesNotExist:
        raise NotFound(f"School {school_id} not found.")
    if not can_view_school(user, partner):
        raise PermissionDenied()
    if _classify(user) != "admin":
        from sessionops.services.progression.freeze import is_school_frozen

        if is_school_frozen(school_id):
            # Hidden from COs/CHOs while it is being progressed (F-M10-5).
            raise NotFound(f"School {school_id} not found.")
    return partner


def require_admin_scope(user: User) -> None:
    """Raise PermissionDenied if the user does not have admin scope."""
    from sessionops.exceptions import PermissionDenied

    if _classify(user) != "admin":
        raise PermissionDenied("Admin scope required.")
