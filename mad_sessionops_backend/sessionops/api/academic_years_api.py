from ninja import Router

from sessionops.schemas.academic_year import (
    AcademicYearCreateIn,
    AcademicYearOut,
    AcademicYearUpdateIn,
)
from sessionops.services.academic_year.queries import (
    create_academic_year,
    get_active_academic_year,
    get_all_academic_years,
    remove_academic_year,
    update_academic_year,
)
from sessionops.services.rbac.scope import require_admin_scope

academic_years_router = Router(tags=["Academic Years"])


@academic_years_router.get("/active/", response=AcademicYearOut, auth=None)
def get_active_year(request):
    """Return the single currently-active academic year."""
    return get_active_academic_year()


@academic_years_router.get("/admin/", response=list[AcademicYearOut])
def list_academic_years(request):
    """Admin-only: list all academic years."""
    require_admin_scope(request.auth)
    return get_all_academic_years()


@academic_years_router.post("/admin/", response={201: AcademicYearOut})
def create_year(request, payload: AcademicYearCreateIn):
    """Admin-only: create the next academic year (starts inactive; becomes active when
    the first Year Progression run into it starts)."""
    require_admin_scope(request.auth)
    return 201, create_academic_year(payload, request.auth)


@academic_years_router.patch("/admin/{academic_year_id}/", response=AcademicYearOut)
def update_year(request, academic_year_id: int, payload: AcademicYearUpdateIn):
    """Admin-only: fix the label of an inactive year that no school uses yet."""
    require_admin_scope(request.auth)
    return update_academic_year(academic_year_id, payload, request.auth)


@academic_years_router.delete("/admin/{academic_year_id}/", response={204: None})
def remove_year(request, academic_year_id: int):
    """Admin-only: remove an inactive year that no school or progression run uses."""
    require_admin_scope(request.auth)
    remove_academic_year(academic_year_id, request.auth)
    return 204, None
