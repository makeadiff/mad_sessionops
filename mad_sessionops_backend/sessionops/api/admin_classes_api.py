"""F-M10-1: Admin → Classes (class catalog). ADMIN_ROLES only (not CXO)."""

from typing import List

from ninja import Router

from sessionops.exceptions import PermissionDenied
from sessionops.schemas.auth import ErrorResponseSchema
from sessionops.schemas.catalog import AdminClassCreateIn, AdminClassOut, AdminClassPatchIn
from sessionops.services.auth.role_helpers import user_has_admin_access
from sessionops.services.catalog.queries import list_catalog
from sessionops.services.catalog.write import create_class, update_class

admin_classes_router = Router(tags=["admin-classes"])


def _require_admin(user) -> None:
    if not user_has_admin_access(user.user_role):
        raise PermissionDenied()


def _reload(class_id: int):
    return list_catalog().get(pk=class_id)


@admin_classes_router.get("/", response={200: List[AdminClassOut], 403: ErrorResponseSchema})
def list_classes(request):
    _require_admin(request.auth)
    return 200, list(list_catalog())


@admin_classes_router.post(
    "/",
    response={
        201: AdminClassOut,
        400: ErrorResponseSchema,
        403: ErrorResponseSchema,
        409: ErrorResponseSchema,
    },
)
def post_class(request, payload: AdminClassCreateIn):
    _require_admin(request.auth)
    cls = create_class(payload, request.auth)
    return 201, _reload(cls.pk)


@admin_classes_router.patch(
    "/{class_id}/",
    response={
        200: AdminClassOut,
        400: ErrorResponseSchema,
        403: ErrorResponseSchema,
        404: ErrorResponseSchema,
        409: ErrorResponseSchema,
    },
)
def patch_class(request, class_id: int, payload: AdminClassPatchIn):
    _require_admin(request.auth)
    cls = update_class(class_id, payload, request.auth)
    return 200, _reload(cls.pk)
