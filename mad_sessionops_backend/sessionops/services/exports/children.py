"""F-M9-2: children roster export rows.

Filters pass straight through to list_children so the CSV matches the
Children tab (same query, same annotations).
"""

from django.db.models import OuterRef, Subquery

from sessionops.models import Child, ChildRemovalLog, Partner
from sessionops.models.child import REMOVED_REASONS
from sessionops.services.children.queries import (
    annotate_current_placement,
    filter_child_status,
    list_children,
)

CHILDREN_HEADER = [
    "child_id",
    "first_name",
    "last_name",
    "gender",
    "date_of_birth",
    "age",
    "class",
    "bucket",
    "status",
    "date_of_enrollment",
    "mad_joining_date",
    "mother_tongue",
    "city",
    "removed_reason",
    "removal_details",
    "removed_on",
]

# "school_city", not "city": the roster already has the child's own city column.
ALL_CHILDREN_HEADER = ["school_id", "school_name", "school_city", *CHILDREN_HEADER]

_REASON_LABELS = dict(REMOVED_REASONS)


def _current_removal(field: str) -> Subquery:
    # deactivate_child writes an active log row; reactivate_child retires it.
    return Subquery(
        ChildRemovalLog.objects.filter(child_id=OuterRef("pk"), is_active=True, removed=False)
        .order_by("-removed_datetime")
        .values(field)[:1]
    )


_ORDER = (
    "current_class_name",
    "current_section_display_name",
    "current_section_name",
    "first_name",
    "last_name",
    "child_id",
)


def _with_removal(qs):
    return qs.annotate(
        _removed_reason=_current_removal("removed_reason"),
        _removal_details=_current_removal("other_details"),
        _removed_on=_current_removal("removed_datetime"),
    )


def _child_row(child) -> list:
    inactive = not child.is_active
    reason = child._removed_reason if inactive else None
    return [
        child.child_id,
        child.first_name,
        child.last_name,
        child.get_gender_display(),
        child.date_of_birth,
        child.age,
        child.current_class_name,
        child.current_section_display_name or child.current_section_name,
        "inactive" if inactive else "active",
        child.date_of_enrollment,
        child.mad_joining_date,
        child.mother_tongue,
        child.city,
        _REASON_LABELS.get(reason, reason) if reason else None,
        child._removal_details if inactive else None,
        child._removed_on if inactive else None,
    ]


def school_children_rows(
    school_id: int,
    *,
    status: str = "all",
    search: str | None = None,
    class_id: int | None = None,
    section_id: int | None = None,
    unassigned: bool = False,
) -> list[list]:
    """Rows for the Children-tab export, ordered class → bucket → name."""
    qs = list_children(
        school_id,
        status=status,
        search=search,
        class_id=class_id,
        section_id=section_id,
        unassigned=unassigned,
    )
    return [_child_row(c) for c in _with_removal(qs).order_by(*_ORDER)]


def all_children_rows(partner_ids: list[int], *, status: str = "all") -> list[list]:
    """F-M9-6: children across the given schools, prefixed with school columns.

    One query for all schools; order is school (as given — export_school_ids
    orders by name), then class → bucket → name.
    """
    if not partner_ids:
        return []
    schools = {
        p.partner_id: p
        for p in Partner.objects.filter(partner_id__in=partner_ids).only(
            "partner_id", "partner_name", "city"
        )
    }
    position = {pid: i for i, pid in enumerate(partner_ids)}
    qs = annotate_current_placement(
        filter_child_status(Child.objects.filter(school_id__in=partner_ids), status)
    )
    children = sorted(
        _with_removal(qs).order_by(*_ORDER), key=lambda c: position[c.school_id]
    )  # stable sort keeps class → bucket → name within each school
    return [
        [
            c.school_id,
            schools[c.school_id].partner_name,
            schools[c.school_id].city,
            *_child_row(c),
        ]
        for c in children
    ]
