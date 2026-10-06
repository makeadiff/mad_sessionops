from django.db.models import Q, QuerySet

from sessionops.models import User
from sessionops.services.rbac.scope import schools_visible_to


def filter_schools_like_page(qs: QuerySet, search: str | None) -> QuerySet:
    """Match the Schools page's in-browser search (SchoolListPage.visibleSchools):
    name, city or CO name, case-insensitive; blank-after-trim means no filter,
    otherwise the raw text is matched. Export-only — GET /api/schools/?search=
    keeps its M1 name/city/state behaviour (TC-M1-4-06)."""
    if not (search or "").strip():
        return qs
    return qs.filter(
        Q(partner_name__icontains=search) | Q(city__icontains=search) | Q(co_name__icontains=search)
    ).distinct()


def export_school_ids(user: User, search: str | None = None) -> list[int]:
    """Partner ids a cross-school export covers: the user's view scope (R13),
    narrowed like the Schools page search, ordered by school name."""
    qs = filter_schools_like_page(schools_visible_to(user), search)
    return list(qs.order_by("partner_name", "partner_id").values_list("partner_id", flat=True))
