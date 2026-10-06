from ninja import Router

from sessionops.exceptions import NotFound
from sessionops.models import Partner
from sessionops.schemas.schools import (
    ChoOut,
    SchoolDetailSchema,
    SchoolListItemSchema,
    SchoolListResponseSchema,
    SchoolSummarySchema,
)
from sessionops.services.rbac import get_scope_warning, schools_visible_to
from sessionops.services.rbac.scope import frozen_schools_in_scope_count
from sessionops.services.schools.queries import (
    filter_schools_by_search,
    get_active_academic_year_label,
    get_active_volunteers_count,
    get_chos_for_school,
    get_school_stats,
)

schools_router = Router(tags=["Schools"])


def _compute_initials(name: str) -> str:
    words = [w for w in name.split() if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return name[:2].upper() if name else "??"


def _to_item(partner: Partner, stats: dict) -> SchoolListItemSchema:
    updated_at = partner.partner_updated_date or partner.synced_at
    return SchoolListItemSchema(
        partner_id=partner.partner_id,
        name=partner.partner_name,
        initials=_compute_initials(partner.partner_name),
        city=partner.city,
        contact_person_name=partner.poc_name,
        contact_phone=partner.poc_contact,
        co_name=partner.co_name,
        setup_status="not_configured",  # M1: no classes/sections yet
        children_count=stats.get("children_count", 0),
        volunteers_count=stats.get("volunteers_count", 0),
        assignments_count=stats.get("assignments_count", 0),
        classes_count=stats.get("classes_count", 0),
        academic_year_label=stats.get("academic_year_label"),
        updated_at=updated_at,
    )


@schools_router.get("", response=SchoolListResponseSchema)
def list_schools(request):
    qs = schools_visible_to(request.auth)
    scope_warning = get_scope_warning(request.auth)

    qs = filter_schools_by_search(qs, request.GET.get("search"))

    partners = list(qs.order_by("-partner_updated_date", "-synced_at"))
    partner_ids = [p.partner_id for p in partners]
    stats_by_school = get_school_stats(partner_ids)
    schools = [_to_item(p, stats_by_school.get(p.partner_id, {})) for p in partners]

    summary = SchoolSummarySchema(
        total_schools=len(schools),
        fully_configured=sum(1 for s in schools if s.setup_status == "configured"),
        children_enrolled=sum(s.children_count for s in schools),
        active_volunteers=get_active_volunteers_count(partner_ids),
        academic_year=get_active_academic_year_label(),
    )

    return SchoolListResponseSchema(
        schools=schools,
        summary=summary,
        scope_warning=scope_warning,
        progressing_count=frozen_schools_in_scope_count(request.auth),
    )


@schools_router.get("/{partner_id}", response=SchoolDetailSchema)
def get_school(request, partner_id: int):
    try:
        partner = schools_visible_to(request.auth).get(partner_id=partner_id)
    except Partner.DoesNotExist:
        raise NotFound("School not found")

    stats = get_school_stats([partner_id]).get(partner_id, {})
    chos = [
        ChoOut(user_id=u.user_id, user_display_name=u.user_display_name)
        for u in get_chos_for_school(partner_id)
    ]

    return SchoolDetailSchema(
        partner_id=partner.partner_id,
        partner_name=partner.partner_name,
        address_line_1=partner.address_line_1,
        address_line_2=partner.address_line_2,
        city=partner.city,
        state=partner.state,
        pincode=partner.pincode,
        school_type=partner.school_type,
        partner_affiliation_type=partner.partner_affiliation_type,
        poc_name=partner.poc_name,
        poc_email=partner.poc_email,
        poc_designation=partner.poc_designation,
        poc_contact=partner.poc_contact,
        mou_sign_date=partner.mou_sign_date,
        mou_start_date=partner.mou_start_date,
        mou_end_date=partner.mou_end_date,
        mou_url=partner.mou_url,
        co_id=partner.co_id,
        co_name=partner.co_name,
        chos=chos,
        synced_at=partner.synced_at,
        configuration_status="awaiting_setup",
        children_count=stats.get("children_count", 0),
        confirmed_child_count=partner.confirmed_child_count,
        classes_count=stats.get("classes_count", 0),
        volunteers_count=stats.get("volunteers_count", 0),
        assignments_count=stats.get("assignments_count", 0),
        academic_year_label=stats.get("academic_year_label"),
    )
