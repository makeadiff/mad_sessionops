"""F-M10-6: which converted schools can be selected for a run.

Each school moves from its own year to the year after it, so schools on
different years can be selected together; nothing waits for stragglers.
"""

from sessionops.models import Partner
from sessionops.services.progression.freeze import frozen_school_ids
from sessionops.services.progression.planner import build_plans
from sessionops.services.progression.target import active_year, label_start

_INELIGIBLE = (
    "ALREADY_IN_RUN",
    "NO_ACTIVE_SCHOOL_YEAR",
    "NO_NEXT_YEAR",
)


def eligible_schools() -> dict:
    """Every active converted school with its current and next year, and whether it
    can be selected. `years_behind` = how far its current year trails the active one."""
    active = active_year()
    partners = list(Partner.objects.filter(converted=True).order_by("partner_name", "partner_id"))
    plans = build_plans([p.partner_id for p in partners], frozen_ids=frozen_school_ids())
    out = []
    for p in partners:
        plan = plans[p.partner_id]
        reasons = [b for b in plan.blockers if b["code"] in _INELIGIBLE]
        behind = (
            max(0, label_start(active.label) - label_start(plan.current_year_label))
            if active and plan.current_year_label
            else 0
        )
        out.append(
            {
                "school_id": p.partner_id,
                "school_name": p.partner_name,
                "city": p.city,
                "current_year_label": plan.current_year_label,
                "target_year_label": plan.to_year_label,
                "years_behind": behind,
                "eligible": not reasons,
                "reason": reasons[0]["code"] if reasons else None,
                "reason_message": reasons[0]["message"] if reasons else None,
            }
        )
    return {"active_year_label": active.label if active else None, "schools": out}
