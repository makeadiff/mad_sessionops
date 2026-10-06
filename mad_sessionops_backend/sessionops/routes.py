"""
Django Ninja API routes configuration.

=============================================================================
ROUTE ORGANIZATION
=============================================================================

This file configures all API routes for the MAD Backend.

API Structure:
    /api/v1/auth/*     -> Authentication (register, login, logout, etc.)
    /api/users/*       -> User management (requires auth)
    /health            -> Health check (public)

Two API instances:
1. `api` - Main API with JWT authentication (protected by default)
2. `public_api` - Public API without authentication

=============================================================================
"""

import os
from typing import Literal

from django.http import JsonResponse

import sentry_sdk
from ninja import NinjaAPI
from ninja.errors import ValidationError
from ninja.responses import Response
from pydantic import ValidationError as PydanticValidationError

from sessionops import auth
from sessionops.api.academic_years_api import academic_years_router
from sessionops.api.admin_classes_api import admin_classes_router
from sessionops.api.admin_progression_api import admin_progression_router
from sessionops.api.admin_realtime_events_api import admin_realtime_events_router
from sessionops.api.admin_sync_api import admin_sync_router
from sessionops.api.auth_api import auth_router
from sessionops.api.children_api import children_router
from sessionops.api.exports_api import exports_router, school_exports_router
from sessionops.api.holidays_api import holidays_router
from sessionops.api.migration_api import router as migration_router
from sessionops.api.partner_sync_internal_api import router as partner_sync_internal_router
from sessionops.api.partner_worknode_sync_internal_api import (
    router as partner_worknode_sync_internal_router,
)
from sessionops.api.realtime_sync_api import router as realtime_sync_router
from sessionops.api.schedule_api import schedule_router
from sessionops.api.schools_api import schools_router
from sessionops.api.sessions_api import sessions_router
from sessionops.api.slot_classes_api import slot_classes_router
from sessionops.api.slots_api import slots_router
from sessionops.api.structure_api import classes_catalog_router, structure_router
from sessionops.api.user_api import user_router
from sessionops.api.volunteers_api import volunteers_router
from sessionops.exceptions import AuthenticationError, ConflictError, NotFound, PermissionDenied
from sessionops.exceptions import ValidationError as BusinessValidationError

# =============================================================================
# MAIN API (Protected by default)
# =============================================================================
# Routes here require JWT authentication unless explicitly disabled
# with auth=None on individual endpoints
# =============================================================================

api = NinjaAPI(
    urls_namespace="api",
    title="MAD Backend APIs",
    description="""
    MAD Sourcing Backend API.

    ## Authentication

    Most endpoints require JWT authentication. Include the access token
    in the Authorization header:

    ```
    Authorization: Bearer <access_token>
    ```

    ### Getting Tokens

    1. **Register**: POST /api/v1/auth/register
    2. **Login**: POST /api/v1/auth/login
    3. **Google OAuth**: POST /api/v1/auth/google

    ### Token Refresh

    When access token expires, use the refresh token:
    POST /api/v1/auth/refresh

    ## Error Responses

    All errors follow this format:
    ```json
    {
        "detail": "Error message"
    }
    ```

    Common status codes:
    - 400: Bad Request (validation error)
    - 401: Unauthorized (invalid/expired token)
    - 403: Forbidden (insufficient permissions)
    - 404: Not Found
    - 409: Conflict (resource already exists)
    - 422: Unprocessable Entity (validation failed)
    - 500: Internal Server Error
    """,
    docs_url="/api/docs",
    # Default authentication for all routes (can be overridden per route)
    auth=auth.CustomJwtAuthMiddleware(),
)


# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================
# These handlers convert exceptions to consistent JSON responses.
#
# Ninja catches exceptions here before they reach Django's own exception
# machinery, so Sentry's DjangoIntegration never sees them on its own —
# each handler must explicitly report to Sentry, tagged with the HTTP
# status so issues can be filtered/segregated in the Sentry UI
# (e.g. `http_status:401`, or `level:error` for real 500s).
# =============================================================================


def _client_ip(request) -> str:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return str(forwarded_for).split(",")[0].strip()
    return str(request.META.get("REMOTE_ADDR", "unknown"))


SentryLevel = Literal["fatal", "critical", "error", "warning", "info", "debug"]


def _report_to_sentry(
    request, exc: Exception, status_code: int, level: SentryLevel = "warning"
) -> None:
    """
    Report an exception with request context regardless of SENTRY_SEND_DEFAULT_PII —
    that setting only controls the DjangoIntegration's own automatic capture, not
    tags we set explicitly here, so caller IP/UA are always available for triage.
    """
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("http_status", status_code)
        scope.set_tag("client_ip", _client_ip(request))
        scope.set_tag("path", request.path)
        scope.set_context(
            "request_meta",
            {
                "user_agent": request.META.get("HTTP_USER_AGENT", "unknown"),
                "has_authorization_header": bool(request.headers.get("Authorization")),
            },
        )
        scope.set_level(level)
        sentry_sdk.capture_exception(exc)


@api.exception_handler(ValidationError)
def ninja_validation_error_handler(request, exc):
    """
    Handle Django Ninja validation errors.

    These are raised when request payload doesn't match the expected schema.
    Returns 422 Unprocessable Entity with error details.
    """
    _report_to_sentry(request, exc, 422)
    return Response({"detail": exc.errors}, status=422)


@api.exception_handler(PydanticValidationError)
def pydantic_validation_error_handler(request, exc: PydanticValidationError):
    """
    Handle Pydantic validation errors.

    These are raised during schema validation (both request and response).
    Returns 400 Bad Request with error details.
    """
    _report_to_sentry(request, exc, 400)
    return Response({"detail": exc.errors()}, status=400)


@api.exception_handler(AuthenticationError)
def auth_error_handler(request, exc: AuthenticationError):
    _report_to_sentry(request, exc, 401)
    return JsonResponse(
        {"error": {"code": "auth_failed", "message": "Authentication failed"}},
        status=401,
    )


@api.exception_handler(PermissionDenied)
def permission_denied_handler(request, exc: PermissionDenied):
    _report_to_sentry(request, exc, 403)
    return JsonResponse(
        {"error": {"code": "permission_denied", "message": "Permission denied"}},
        status=403,
    )


@api.exception_handler(BusinessValidationError)
def business_validation_error_handler(request, exc: BusinessValidationError):
    _report_to_sentry(request, exc, 400)
    return JsonResponse(
        {"error": {"code": "validation_error", "message": exc.message}},
        status=400,
    )


@api.exception_handler(NotFound)
def not_found_handler(request, exc: NotFound):
    _report_to_sentry(request, exc, 404)
    return JsonResponse(
        {"error": {"code": "not_found", "message": exc.message}},
        status=404,
    )


@api.exception_handler(ConflictError)
def conflict_error_handler(request, exc: ConflictError):
    _report_to_sentry(request, exc, 409)
    return JsonResponse(
        # A specific error_code (e.g. "undo_not_allowed", M10) passes through; the
        # default "CONFLICT" keeps the long-standing "conflict" code.
        {
            "error": {
                "code": "conflict" if exc.error_code == "CONFLICT" else exc.error_code,
                "message": exc.message,
            }
        },
        status=409,
    )


@api.exception_handler(Exception)
def ninja_default_error_handler(request, exc: Exception):
    """Catch-all — prevents raw tracebacks leaking to clients."""
    _report_to_sentry(request, exc, 500, level="error")
    return Response({"detail": str(exc)}, status=500)


# =============================================================================
# ROUTE REGISTRATION
# =============================================================================
# Mount routers from api modules
# =============================================================================

# Authentication routes (mostly public — auth=None on individual routes)
# Prefix: /api/auth/
api.add_router("/api/auth/", auth_router)

# User management routes (requires authentication)
# Prefix: /api/users/
user_router.tags = ["Users"]
api.add_router("/api/users/", user_router)

# Schools routes (scope-filtered by RBAC)
# Prefix: /api/schools/
api.add_router("/api/schools/", schools_router)

# Academic year routes
# Prefix: /api/academic-years/
api.add_router("/api/academic-years/", academic_years_router)

# Structure routes (school-scoped: classes + sections)
# Prefix: /api/schools/{school_id}/classes/, /api/schools/{school_id}/sections/
api.add_router("/api/schools/", structure_router)

# Class catalog (global, not school-scoped): /api/classes/, /api/classes/section-codes/
api.add_router("/api/classes/", classes_catalog_router)

# Children routes (school-scoped: enroll, edit, deactivate, reactivate, list)
api.add_router("/api/schools/", children_router)

# Volunteers routes (school-scoped: list auto-populated from Worknode)
api.add_router("/api/schools/", volunteers_router)

# Slots routes (school-scoped: CRUD)
api.add_router("/api/schools/", slots_router)

# Slot-classes routes (slot-scoped: CRUD)
api.add_router("/api/schools/", slot_classes_router)

# Schedule view (school-scoped: read-only weekly schedule)
api.add_router("/api/schools/", schedule_router)

# Sessions (school-scoped: configure academic session window)
api.add_router("/api/schools/", sessions_router)

# Holidays (school-scoped: CRUD within session window)
api.add_router("/api/schools/", holidays_router)

# M9 CSV exports (per-school: /api/schools/{id}/exports/*; cross-school: /api/exports/*)
api.add_router("/api/schools/", school_exports_router)
api.add_router("/api/exports/", exports_router)

# Admin sync dashboard (admin-only read endpoints)
api.add_router("/api/admin/", admin_sync_router)

# Admin → Classes: class catalog management (F-M10-1)
api.add_router("/api/admin/classes/", admin_classes_router)

# Admin → Year Progression (M10)
api.add_router("/api/admin/progression/", admin_progression_router)

# Admin realtime events — list, detail, manual sync trigger
api.add_router("/api/admin/realtime-events", admin_realtime_events_router)

# Internal realtime sync endpoint (path from env var, auth handled inside the router)
_internal_sync_path = os.getenv("INTERNAL_SYNC_ENDPOINT_PATH", "/sync-user-internal")
api.add_router(_internal_sync_path, realtime_sync_router)

# Internal partner-sync trigger endpoint (path from env var, auth handled inside the
# router) — n8n scheduler replaces the crontab entry, calling this on its own schedule
_partner_sync_path = os.getenv("PARTNER_SYNC_ENDPOINT_PATH", "/sync-partner-internal")
api.add_router(_partner_sync_path, partner_sync_internal_router)

# Internal partner-worknode-sync trigger endpoint (path from env var, auth handled
# inside the router) — n8n scheduler for daily partner_worknode sync runs
_partner_worknode_sync_path = os.getenv(
    "PARTNER_WORKNODE_SYNC_ENDPOINT_PATH", "/sync-partner-worknode-internal"
)
api.add_router(_partner_worknode_sync_path, partner_worknode_sync_internal_router)

# Internal migration loader endpoints (F-M7-1) — fixed prefix, token-only auth
# handled inside the router (see sessionops/api/migration_api.py)
api.add_router("/api/internal/migrate/", migration_router)


# =============================================================================
# PUBLIC API (No Authentication)
# =============================================================================
# Routes here are accessible without authentication
# Use for health checks, public endpoints, etc.
# =============================================================================

public_api = NinjaAPI(
    urls_namespace="public-api",
    title="Public MAD APIs",
    description="Public endpoints - no authentication required",
    docs_url="/api/v1/public/docs",
)


@public_api.get("/health")
def health_check(request):
    """
    Health check endpoint for load balancers and monitoring.

    Returns:
        200 OK with status information

    Example Response:
        {
            "status": "healthy",
            "service": "mad_backend"
        }
    """
    return {"status": "healthy", "service": "mad_backend"}
