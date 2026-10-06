"""F-M10-6: precheck, preview and the graduation child picker — all read-only."""

from django.db.models import Q

from sessionops.models import Child, ChildClass
from sessionops.services.children.queries import annotate_current_placement
from sessionops.services.progression.freeze import frozen_school_ids
from sessionops.services.progression.planner import Marks, build_plans, validate_marks


def _issues(items: list[dict]) -> list[dict]:
    return [{"code": i["code"], "message": i["message"]} for i in items]


def _base(plan) -> dict:
    return {
        "school_id": plan.school_id,
        "school_name": plan.school_name,
        "current_year_label": plan.current_year_label,
        "target_year_label": plan.to_year_label,
        "status": plan.status,
        "blockers": _issues(plan.blockers),
        "warnings": _issues(plan.warnings),
    }


def precheck(school_ids: list[int]) -> list[dict]:
    ids = list(dict.fromkeys(school_ids))
    plans = build_plans(ids, frozen_ids=frozen_school_ids())
    return [_base(plans[sid]) for sid in ids]


def preview(schools: list[dict]) -> list[dict]:
    marks: dict[int, Marks] = {}
    for s in schools:
        m = Marks(
            set(s.get("graduate_class_ids") or []),
            set(s.get("graduate_child_ids") or []),
        )
        validate_marks(s["school_id"], m)
        marks[s["school_id"]] = m
    ids = list(dict.fromkeys(s["school_id"] for s in schools))
    plans = build_plans(ids, marks, frozen_ids=frozen_school_ids())
    return [{**_base(plans[sid]), "counts": plans[sid].counts} for sid in ids]


def preview_children(
    school_id: int,
    *,
    class_id: int | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Active children of the school with their current placement, for picking
    individual graduations. Only id, name, class and section (no DOB or contact)."""
    qs = annotate_current_placement(
        Child.objects.filter(school_id=school_id, is_active=True, removed=False)
    )
    if class_id:
        child_ids = ChildClass.objects.filter(
            is_active=True, removed=False, school_class_id__class_id=class_id
        ).values("child_id")
        qs = qs.filter(pk__in=child_ids)
    if search and search.strip():
        term = search.strip()
        qs = qs.filter(Q(first_name__icontains=term) | Q(last_name__icontains=term))
    qs = qs.order_by("first_name", "last_name", "child_id")

    total = qs.count()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = list(qs[(page - 1) * page_size : page * page_size])
    class_ids = dict(
        ChildClass.objects.filter(
            child_id__in=[c.pk for c in rows], is_active=True, removed=False
        ).values_list("child_id", "school_class_id__class_id")
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": [
            {
                "child_id": c.pk,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "class_id": class_ids.get(c.pk),
                "class_name": getattr(c, "current_class_name", None),
                "section_name": getattr(c, "current_section_display_name", None)
                or getattr(c, "current_section_name", None),
            }
            for c in rows
        ],
    }
