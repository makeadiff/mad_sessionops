from django.db import IntegrityError, transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from sessionops.exceptions import ConflictError, NotFound
from sessionops.models import ChildClassSection, ClassSection, SchoolClass, SlotClassSection
from sessionops.models.class_section import SECTION_CODES
from sessionops.services.academic_year.queries import (
    current_year_q,
    get_or_create_school_academic_year,
)
from sessionops.services.sections.slug import next_default_display_name, normalize_section_slug


def _in_current_year() -> Q:
    """Sections in the school's own active year; legacy rows with no school-year
    (0 in dev on 2026-09-29) stay visible rather than silently disappearing."""
    return current_year_q() | Q(school_academic_year_id__isnull=True)


def _with_active_children_count(class_section_id: int) -> ClassSection:
    """Re-fetch a ClassSection with active_children_count annotated, for schema resolution."""
    return ClassSection.objects.annotate(
        active_children_count=Count(
            "childclasssection",
            filter=Q(childclasssection__is_active=True, childclasssection__removed=False),
        )
    ).get(class_section_id=class_section_id)


def list_sections_for_class(school_class_id: int) -> QuerySet:
    return (
        ClassSection.objects.filter(
            _in_current_year(), school_class_id=school_class_id, is_active=True, removed=False
        )
        .annotate(
            active_children_count=Count(
                "childclasssection",
                filter=Q(childclasssection__is_active=True, childclasssection__removed=False),
            )
        )
        .order_by("section_code")
    )


def available_section_codes(school_class_id: int) -> list[str]:
    used = set(
        ClassSection.objects.filter(school_class_id=school_class_id, removed=False).values_list(
            "section_code", flat=True
        )
    )
    return [c for c in SECTION_CODES if c not in used]


def add_section_to_class(
    school_class_id: int, school_id: int, section_code: str, user
) -> ClassSection:
    try:
        sc = SchoolClass.objects.select_related("class_id").get(
            school_class_id=school_class_id,
            school_id=school_id,
            is_active=True,
            removed=False,
        )
    except SchoolClass.DoesNotExist:
        raise NotFound(f"School class {school_class_id} not found.")

    section_name = f"{sc.class_id.class_name} - {section_code}"

    try:
        section = ClassSection.objects.create(
            school_class_id=sc,
            school_id=school_id,
            section_code=section_code,
            section_name=section_name,
            # Denormalized from the parent SchoolClass at creation time — never
            # re-derived later, so a section can't drift onto a different AY than
            # the class it was created under.
            school_academic_year_id_id=sc.school_academic_year_id_id,
            created_by=user,
        )
    except IntegrityError:
        raise ConflictError(f"Section {section_code} already exists for this class.")

    return _with_active_children_count(section.class_section_id)


def count_active_children_in_section(class_section_id: int) -> int:
    return ChildClassSection.objects.filter(
        class_section_id=class_section_id, is_active=True, removed=False
    ).count()


def soft_delete_section(class_section_id: int, school_id: int, user) -> None:
    try:
        cs = ClassSection.objects.get(
            class_section_id=class_section_id,
            school_id=school_id,
            is_active=True,
            removed=False,
        )
    except ClassSection.DoesNotExist:
        raise NotFound(f"Section {class_section_id} not found.")

    # M3 extension: block if active slot-class assignments reference this section
    active_scs_count = SlotClassSection.objects.filter(
        class_section_id=cs,
        is_active=True,
        removed=False,
    ).count()
    if active_scs_count > 0:
        raise ConflictError(
            f"Cannot delete this section. Remove the {active_scs_count} class "
            f"assignment{'s' if active_scs_count != 1 else ''} from the schedule first."
        )

    count = count_active_children_in_section(class_section_id)
    if count > 0:
        raise ConflictError(f"Cannot remove section: {count} active child(ren) enrolled.")

    now = timezone.now()
    cs.is_active = False
    cs.removed = True
    cs.deleted_at = now
    cs.updated_by = user
    cs.save(update_fields=["is_active", "removed", "deleted_at", "updated_by", "updated_at"])


# ── Buckets (F-M6-2) ─────────────────────────────────────────────────────────────
#
# A bucket is a ClassSection row with school_class_id=None, section_code=None —
# class-agnostic per M6 decision #1. section_name holds a normalized slug;
# section_display_name holds the CO's original free-text input.


def create_bucket(school_id: int, display_name: str | None, user) -> ClassSection:
    name = display_name or next_default_display_name(school_id)
    slug = normalize_section_slug(name)

    # Same scope as the DB slug constraint (active rows only): an archived bucket from a
    # previous year never blocks re-using its name (F-M10-3).
    if ClassSection.objects.filter(
        school_id=school_id, section_name=slug, is_active=True, removed=False
    ).exists():
        raise ConflictError(f'A bucket named "{name}" already exists in this school.')

    say = get_or_create_school_academic_year(school_id, user)

    try:
        bucket = ClassSection.objects.create(
            school_id=school_id,
            section_name=slug,
            section_display_name=name,
            school_class_id=None,
            section_code=None,
            school_academic_year_id=say,
            created_by=user,
        )
    except IntegrityError:
        raise ConflictError(f'A bucket named "{name}" already exists in this school.')

    return _with_active_children_count(bucket.class_section_id)


@transaction.atomic
def edit_bucket(
    class_section_id: int, school_id: int, display_name: str | None, user
) -> ClassSection:
    try:
        bucket = ClassSection.objects.select_for_update().get(
            class_section_id=class_section_id,
            school_id=school_id,
            is_active=True,
            removed=False,
        )
    except ClassSection.DoesNotExist:
        raise NotFound(f"Bucket {class_section_id} not found.")

    if display_name and display_name != bucket.section_display_name:
        slug = normalize_section_slug(display_name)
        if (
            ClassSection.objects.filter(
                school_id=school_id, section_name=slug, is_active=True, removed=False
            )
            .exclude(class_section_id=class_section_id)
            .exists()
        ):
            raise ConflictError(f'A bucket named "{display_name}" already exists in this school.')

        try:
            bucket.section_name = slug
            bucket.section_display_name = display_name
            bucket.updated_by = user
            bucket.save(
                update_fields=["section_name", "section_display_name", "updated_by", "updated_at"]
            )
        except IntegrityError:
            raise ConflictError(f'A bucket named "{display_name}" already exists in this school.')

    return _with_active_children_count(bucket.class_section_id)


def list_buckets_for_school(school_id: int) -> QuerySet:
    return (
        ClassSection.objects.filter(
            _in_current_year(), school_id=school_id, is_active=True, removed=False
        )
        .annotate(
            active_children_count=Count(
                "childclasssection",
                filter=Q(childclasssection__is_active=True, childclasssection__removed=False),
            )
        )
        .order_by("section_display_name", "section_name")
    )
