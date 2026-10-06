from sessionops.models import PartnerWorknode, SlotClassSectionVolunteer, User
from sessionops.services.academic_year.queries import current_year_q
from sessionops.services.rbac.scope import get_school_or_403


def list_school_volunteers(school_id: int, requesting_user) -> dict:
    """Return volunteers auto-populated from Worknode for this school."""
    get_school_or_403(requesting_user, school_id)

    worknode_ids = list(
        PartnerWorknode.objects.filter(
            partner_id=str(school_id),
        )
        .values_list("worknode_id", flat=True)
        .distinct()
    )

    if not worknode_ids:
        return {
            "status": "no_worknode",
            "message": (
                "No Worknode found for this school. Contact an admin to map it in Platform "
                "Commons before volunteers can be assigned here."
            ),
            "volunteers": [],
        }

    volunteers = list(
        User.objects.filter(
            worknode_id__in=worknode_ids,
            is_active=True,
        ).order_by("user_display_name")
    )

    if not volunteers:
        return {
            "status": "no_volunteers",
            "message": (
                "No volunteers found for this school. To see volunteers here, add this "
                "school's workplace for that user in Platform Commons' user management — "
                "once tagged, they'll appear here and can be assigned to slots and mentoring "
                "circles."
            ),
            "volunteers": [],
        }

    # Only the active academic year's slots count as current assignments.
    in_active_year = current_year_q("slot_class_section_id__slot_id__")
    serialized = []
    for v in volunteers:
        # active_slot_class_section_id: which slot-class (if any) this volunteer
        # currently holds. Since R6 (business_rules.md) limits a volunteer to at
        # most one active slot-class assignment system-wide, this is normally
        # 0-or-1 rows; .values_list(...)[0] picks whichever the DB returns first
        # if legacy/manually-inserted data ever has more than one.
        active_scs_ids = list(
            SlotClassSectionVolunteer.objects.filter(
                in_active_year,
                volunteer_id=v,
                is_active=True,
                removed=False,
                slot_class_section_id__slot_id__school_id=school_id,
            ).values_list("slot_class_section_id_id", flat=True)
        )
        serialized.append(
            {
                "user_id": v.user_id,
                "user_display_name": v.user_display_name,
                "user_login": v.user_login,
                "user_role": v.user_role,
                "email": v.email,
                "contact": v.contact,
                "city": v.city,
                "state": v.state,
                "active_slot_class_count": len(active_scs_ids),
                "active_slot_class_section_id": active_scs_ids[0] if active_scs_ids else None,
            }
        )

    return {"status": "ok", "volunteers": serialized}
