"""
Structure API — classes and sections.

Class endpoints: F-M2-4
Section endpoints: F-M2-5
"""

from ninja import Router

from sessionops.models.class_section import SECTION_CODES
from sessionops.schemas.structure import (
    AvailableCodesOut,
    BucketAddIn,
    BucketChildAddIn,
    BucketChildOut,
    BucketEditIn,
    BucketOut,
    ClassAddIn,
    ClassCatalogItemOut,
    SchoolClassOut,
    SectionAddIn,
    SectionOut,
)
from sessionops.services.catalog.queries import list_open_catalog
from sessionops.services.rbac.scope import get_school_or_403
from sessionops.services.structure.bucket_children import (
    add_child_to_bucket,
    remove_child_from_bucket,
)
from sessionops.services.structure.queries import (
    add_class_to_school,
    list_classes_for_school,
    soft_delete_school_class,
)
from sessionops.services.structure.sections import (
    add_section_to_class,
    available_section_codes,
    create_bucket,
    edit_bucket,
    list_buckets_for_school,
    list_sections_for_class,
    soft_delete_section,
)

structure_router = Router(tags=["Structure"])
classes_catalog_router = Router(tags=["Classes Catalog"])


# ── Global class catalog (no auth required) ────────────────────────────────────


@classes_catalog_router.get("/", response=list[ClassCatalogItemOut], auth=None)
def list_class_catalog(request):
    # Only classes open for new enrolment can be added to a school (F-M10-1);
    # closed ones (e.g. 8th) are reachable via year-end progression only.
    return list_open_catalog()


@classes_catalog_router.get("/section-codes/", auth=None)
def list_section_codes(request):
    return {"codes": SECTION_CODES}


# ── School-scoped class endpoints ──────────────────────────────────────────────


@structure_router.get("/{school_id}/classes/", response=list[SchoolClassOut])
def list_school_classes(request, school_id: int):
    get_school_or_403(request.auth, school_id)
    return list(list_classes_for_school(school_id))


@structure_router.post("/{school_id}/classes/", response={201: SchoolClassOut})
def add_class(request, school_id: int, payload: ClassAddIn):
    get_school_or_403(request.auth, school_id)
    return 201, add_class_to_school(school_id, payload.class_id, request.auth)


@structure_router.delete("/{school_id}/classes/{school_class_id}/", response={204: None})
def remove_class(request, school_id: int, school_class_id: int):
    get_school_or_403(request.auth, school_id)
    soft_delete_school_class(school_class_id, school_id, request.auth)
    return 204, None


# ── Section endpoints ──────────────────────────────────────────────────────────


@structure_router.get("/{school_id}/classes/{school_class_id}/sections/", response=list[SectionOut])
def list_sections(request, school_id: int, school_class_id: int):
    get_school_or_403(request.auth, school_id)
    return list(list_sections_for_class(school_class_id))


@structure_router.get(
    "/{school_id}/classes/{school_class_id}/sections/available-codes/",
    response=AvailableCodesOut,
)
def get_available_codes(request, school_id: int, school_class_id: int):
    get_school_or_403(request.auth, school_id)
    return {"codes": available_section_codes(school_class_id)}


@structure_router.post(
    "/{school_id}/classes/{school_class_id}/sections/",
    response={201: SectionOut},
)
def add_section(request, school_id: int, school_class_id: int, payload: SectionAddIn):
    get_school_or_403(request.auth, school_id)
    return 201, add_section_to_class(school_class_id, school_id, payload.section_code, request.auth)


@structure_router.delete("/{school_id}/sections/{class_section_id}/", response={204: None})
def remove_section(request, school_id: int, class_section_id: int):
    get_school_or_403(request.auth, school_id)
    soft_delete_section(class_section_id, school_id, request.auth)
    return 204, None


# ── Buckets (F-M6-2) ─────────────────────────────────────────────────────────────
# Class-agnostic containers, additive alongside the class-scoped section
# endpoints above. Both operate on the same ClassSection table.


@structure_router.get("/{school_id}/sections/", response=list[BucketOut])
def list_buckets(request, school_id: int):
    get_school_or_403(request.auth, school_id)
    return list(list_buckets_for_school(school_id))


@structure_router.post("/{school_id}/sections/", response={201: BucketOut})
def add_bucket(request, school_id: int, payload: BucketAddIn):
    get_school_or_403(request.auth, school_id)
    return 201, create_bucket(school_id, payload.display_name, request.auth)


@structure_router.patch("/{school_id}/sections/{class_section_id}/", response=BucketOut)
def edit_bucket_view(request, school_id: int, class_section_id: int, payload: BucketEditIn):
    get_school_or_403(request.auth, school_id)
    return edit_bucket(class_section_id, school_id, payload.display_name, request.auth)


# ── Bucket-children membership (F-M6-3) ─────────────────────────────────────────


@structure_router.post(
    "/{school_id}/sections/{section_id}/children/",
    response={201: BucketChildOut},
)
def add_bucket_child(request, school_id: int, section_id: int, payload: BucketChildAddIn):
    get_school_or_403(request.auth, school_id)
    ccs = add_child_to_bucket(school_id, section_id, payload.child_id, request.auth)
    return 201, ccs


@structure_router.delete(
    "/{school_id}/sections/{section_id}/children/{child_id}/",
    response={204: None},
)
def remove_bucket_child(request, school_id: int, section_id: int, child_id: int):
    get_school_or_403(request.auth, school_id)
    remove_child_from_bucket(school_id, section_id, child_id, request.auth)
    return 204, None
