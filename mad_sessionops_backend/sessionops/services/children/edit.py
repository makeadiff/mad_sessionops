from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from sessionops.exceptions import ConflictError, NotFound, ValidationError
from sessionops.models import (
    Child,
    ChildClass,
    ChildClassSection,
    ChildSubject,
    ClassSection,
    ClassSectionSubject,
    SchoolClass,
    User,
)
from sessionops.schemas.children import ChildEditIn
from sessionops.services.catalog.rules import assert_class_open_for_enrolment
from sessionops.services.children.enroll import MAX_CHILDREN_PER_SECTION
from sessionops.services.rbac.scope import get_school_or_403
from sessionops.services.structure.bucket_children import assert_bucket_not_over_volunteered

_DEMOGRAPHIC_FIELDS = [
    "first_name",
    "last_name",
    "gender",
    "age",
    "date_of_birth",
    "city",
    "mother_tongue",
    "date_of_enrollment",
    "mad_joining_date",
]


def edit_child(child_id: int, payload: ChildEditIn, user: User):
    with transaction.atomic():
        # Lock child row to prevent concurrent edits
        try:
            child = Child.objects.select_for_update().get(
                child_id=child_id, is_active=True, removed=False
            )
        except Child.DoesNotExist:
            raise NotFound(f"Child {child_id} not found.")

        # RBAC: CO may only edit children at their assigned schools
        get_school_or_403(user, child.school_id)

        # Update demographic fields (only non-None values from payload)
        update_fields = ["updated_by_id", "updated_at"]
        for field in _DEMOGRAPHIC_FIELDS:
            val = getattr(payload, field, None)
            if val is not None:
                setattr(child, field, val)
                update_fields.append(field)
        child.updated_by = user
        child.save(update_fields=update_fields)

        # Handle explicit class change — independent of any bucket change (M6).
        # No DB constraint backs the one-active-ChildClass invariant (decision #5);
        # the select_for_update() on `child` above serialises concurrent calls.
        if payload.school_class_id is not None:
            current_active_count = ChildClass.objects.filter(
                child_id=child.child_id, is_active=True, removed=False
            ).count()
            if current_active_count > 1:
                raise ValidationError(
                    "Data inconsistency: multiple active class assignments for this "
                    "child. Contact an administrator."
                )
            current_cc = ChildClass.objects.filter(
                child_id=child.child_id, is_active=True, removed=False
            ).first()
            if current_cc is None or current_cc.school_class_id_id != payload.school_class_id:
                try:
                    new_school_class = SchoolClass.objects.select_related("class_id").get(
                        school_class_id=payload.school_class_id,
                        school_id=child.school_id,
                        is_active=True,
                        removed=False,
                    )
                except SchoolClass.DoesNotExist:
                    raise NotFound(f"School class {payload.school_class_id} not found.")

                # Moving a child INTO a class closed for enrolment (e.g. 8th) directly
                # is not allowed — only year-end progression can put them there. A child
                # already sitting in that class is unaffected: this branch only runs
                # when the target class differs from current_cc above.
                assert_class_open_for_enrolment(new_school_class.class_id)

                now = timezone.now()
                if current_cc:
                    current_cc.is_active = False
                    current_cc.removed = True
                    current_cc.deleted_at = now
                    current_cc.updated_by = user
                    current_cc.save()
                ChildClass.objects.create(
                    child_id=child,
                    school_class_id=new_school_class,
                    created_by=user,
                )

        # Handle bucket change — independent of class change (a bucket has no
        # school_class_id to follow, unlike legacy M2/M3 sections).
        if payload.class_section_id is not None:
            try:
                new_section = ClassSection.objects.select_for_update().get(
                    class_section_id=payload.class_section_id,
                    is_active=True,
                    removed=False,
                )
            except ClassSection.DoesNotExist:
                raise NotFound(f"Section {payload.class_section_id} not found.")

            # Cross-school guard
            if new_section.school_id != child.school_id:
                raise ValidationError("Target section belongs to a different school.")

            now = timezone.now()
            current_ccs = ChildClassSection.objects.filter(
                child_id=child.child_id, is_active=True, removed=False
            ).first()

            # Only create history rows when the section actually changes
            if current_ccs is None or current_ccs.class_section_id_id != payload.class_section_id:
                # R-bucket: vacating the OLD bucket must not silently leave a
                # scheduled slot-class over-volunteered, same guard
                # remove_child_from_bucket already applies. Lock the old
                # bucket (a different row from `new_section`, already locked
                # above) before checking, to avoid a lost-update race against
                # a concurrent removal/move on that same old bucket.
                if current_ccs is not None:
                    old_bucket = ClassSection.objects.select_for_update().get(
                        pk=current_ccs.class_section_id_id
                    )
                    assert_bucket_not_over_volunteered(
                        old_bucket, current_ccs.child_class_section_id
                    )

                # Capacity check on the target section
                occupied = ChildClassSection.objects.filter(
                    class_section_id=new_section, is_active=True, removed=False
                ).count()
                if occupied >= MAX_CHILDREN_PER_SECTION:
                    raise ConflictError(
                        f"Section is full ({MAX_CHILDREN_PER_SECTION}/{MAX_CHILDREN_PER_SECTION})."
                    )

                # Soft-delete current ChildClassSection (if any)
                if current_ccs:
                    current_ccs.is_active = False
                    current_ccs.removed = True
                    current_ccs.deleted_at = now
                    current_ccs.updated_by = user
                    current_ccs.save()

                # Insert new ChildClassSection
                ChildClassSection.objects.create(
                    child_id=child,
                    class_section_id=new_section,
                    created_by=user,
                )

                # Backfill ChildSubject for the new bucket's active subjects,
                # idempotently. Old ChildSubject rows are intentionally left
                # untouched (never soft-deleted) — Dots needs the full history
                # of every subject a child was ever attached to (M6 decision #2).
                new_active_css = list(
                    ClassSectionSubject.objects.filter(
                        class_section_id=new_section,
                        is_active=True,
                        removed=False,
                    )
                )
                for css in new_active_css:
                    ChildSubject.objects.get_or_create(
                        child_id=child,
                        class_section_subject_id=css,
                        defaults={"created_by": user},
                    )

    # Re-fetch with annotations for serialization
    from sessionops.services.children.queries import list_children

    return list_children(child.school_id).get(child_id=child_id)
