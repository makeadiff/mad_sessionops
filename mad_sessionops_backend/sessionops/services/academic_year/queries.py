from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from sessionops.exceptions import ConflictError, NotFound, ValidationError
from sessionops.models import AcademicYear, SchoolAcademicYear
from sessionops.schemas.academic_year import AcademicYearCreateIn, AcademicYearUpdateIn


def get_active_academic_year() -> AcademicYear:
    try:
        return AcademicYear.objects.get(is_active=True, removed=False)
    except AcademicYear.DoesNotExist:
        raise NotFound("No active academic year is configured.")


def current_year_q(prefix: str = "") -> Q:
    """Q limiting rows to the school's own active school-year (F-M10-3).

    `prefix` is the lookup path from the queried model to the model that carries
    `school_academic_year_id` — "" for Slot / SchoolClass / ClassSection /
    SchoolVolunteer / BatchChild / SchoolHoliday, "slot_id__" for SlotClassSection,
    "slot_class_section_id__slot_id__" for SlotClassSectionVolunteer,
    "class_section_id__" for ChildClassSection, "school_class_id__" for ChildClass.

    Each school has exactly one active school-year (R8a / F-M10-2), so this is
    correct for single- and cross-school queries alike, and it needs no extra
    query. A school that hasn't been progressed keeps seeing its own year; after
    progression archives the old school-year, its rows drop out everywhere.
    Rows with no school-year (legacy) never match.
    """
    return Q(
        **{
            f"{prefix}school_academic_year_id__is_active": True,
            f"{prefix}school_academic_year_id__removed": False,
        }
    )


def get_all_academic_years() -> list[AcademicYear]:
    """Non-removed years, newest first, each annotated with `school_count` (how many
    schools have a school-year on it, any state) and `can_remove`."""
    years: list[AcademicYear] = list(
        AcademicYear.objects.filter(removed=False)
        .annotate(school_count=Count("schoolacademicyear", distinct=True))
        .order_by("-academic_year_id")
    )
    in_runs = _years_in_progression_runs()
    for y in years:
        # Read by AcademicYearOut's resolvers (plain attributes on the instance).
        y.can_remove = (  # type: ignore[attr-defined]  # ad-hoc attribute for the response
            not y.is_active and getattr(y, "school_count", 0) == 0 and y.pk not in in_runs
        )
    return years


def _label_start(label: str) -> int:
    return int(label.split("-", 1)[0])


def _years_in_progression_runs() -> set[int]:
    from sessionops.models import ProgressionRun

    ids: set[int] = set()
    for a, b in ProgressionRun.objects.values_list("from_academic_year_id", "to_academic_year_id"):
        ids.update((a, b))
    return ids


def _assert_is_next_year(label: str, exclude_id: int | None = None) -> None:
    """Only the year right after the latest existing one may be added (no gaps).

    Stops a typo (e.g. 2028-2029 while 2026-2027 is the latest) from becoming the
    year progression moves every school into.
    """
    others = AcademicYear.objects.filter(removed=False)
    if exclude_id is not None:
        others = others.exclude(academic_year_id=exclude_id)
    starts = [_label_start(lbl) for lbl in others.values_list("label", flat=True)]
    if not starts:
        return
    expected = max(starts) + 1
    if _label_start(label) != expected:
        raise ValidationError(
            f"The next academic year must be {expected}-{expected + 1} "
            f"(the latest is {expected - 1}-{expected})."
        )


def _assert_unused(year: AcademicYear, action: str) -> None:
    if year.is_active:
        raise ConflictError(f"{year.label} is the active academic year and cannot be {action}.")
    used = SchoolAcademicYear.objects.filter(academic_year_id=year).count()
    if used:
        raise ConflictError(
            f"{year.label} is already used by {used} school(s) and cannot be {action}."
        )
    if year.pk in _years_in_progression_runs():
        raise ConflictError(f"{year.label} is part of a progression run and cannot be {action}.")


def _get_year(academic_year_id: int, *, lock: bool = False) -> AcademicYear:
    qs = AcademicYear.objects.all()
    if lock:
        qs = qs.select_for_update()
    try:
        return qs.get(academic_year_id=academic_year_id, removed=False)
    except AcademicYear.DoesNotExist:
        raise NotFound(f"Academic year {academic_year_id} not found.")


@transaction.atomic
def create_academic_year(payload: AcademicYearCreateIn, user) -> AcademicYear:
    if AcademicYear.objects.filter(label=payload.label, removed=False).exists():
        raise ConflictError(f"Academic year '{payload.label}' already exists.")
    _assert_is_next_year(payload.label)
    # `label` is unique at the DB level: re-adding a removed year restores it.
    removed = AcademicYear.objects.filter(label=payload.label, removed=True).first()
    if removed is not None:
        removed.removed = False
        removed.is_active = False
        removed.deleted_at = None
        removed.updated_by = user
        removed.save(
            update_fields=["removed", "is_active", "deleted_at", "updated_by", "updated_at"]
        )
        return removed
    return AcademicYear.objects.create(
        label=payload.label,
        is_active=False,
        created_by=user,
    )


@transaction.atomic
def update_academic_year(
    academic_year_id: int, payload: AcademicYearUpdateIn, user=None
) -> AcademicYear:
    """Fix a label — only for an inactive year no school uses yet, and only to a
    label that keeps the years gap-free."""
    year = _get_year(academic_year_id, lock=True)
    if payload.label == year.label:
        return year
    if (
        AcademicYear.objects.filter(label=payload.label, removed=False)
        .exclude(academic_year_id=academic_year_id)
        .exists()
    ):
        raise ConflictError(f"Academic year '{payload.label}' already exists.")
    _assert_unused(year, "renamed")
    _assert_is_next_year(payload.label, exclude_id=year.pk)

    year.label = payload.label
    year.updated_by = user
    year.save(update_fields=["label", "updated_by", "updated_at"])
    return year


@transaction.atomic
def remove_academic_year(academic_year_id: int, user) -> None:
    """Soft-remove an inactive year that no school or progression run uses (R9)."""
    year = _get_year(academic_year_id, lock=True)
    _assert_unused(year, "removed")
    year.removed = True
    year.deleted_at = timezone.now()
    year.updated_by = user
    year.save(update_fields=["removed", "deleted_at", "updated_by", "updated_at"])


def get_school_academic_year(school_id: int) -> SchoolAcademicYear | None:
    """The school's single active school-year (DB-guaranteed unique, F-M10-2), or None."""
    return SchoolAcademicYear.objects.filter(
        school_id=school_id, is_active=True, removed=False
    ).first()


def get_or_create_school_academic_year(school_id: int, user) -> SchoolAcademicYear:
    """
    Return the school's currently-active SchoolAcademicYear binding, creating one
    against the globally-active AcademicYear only if the school has no active
    binding at all.

    A school's active binding is independent of which AcademicYear is globally
    active — a school can be mid-progression on a year that's no longer current
    (see services/schools/queries.py's academic_year_by_school). So this must NOT
    look the row up scoped to the globally-active year: doing that finds no match
    once the global year rolls over and creates a second active row for the
    school, leaving it with two simultaneously-active SchoolAcademicYear rows.
    """
    existing = get_school_academic_year(school_id)
    if existing is not None:
        return existing

    active_year = get_active_academic_year()
    try:
        # Savepoint: a concurrent first write for the same school can win the race;
        # uniq_active_say_per_school then rejects ours and we use theirs.
        with transaction.atomic():
            return SchoolAcademicYear.objects.create(
                school_id=school_id,
                academic_year_id=active_year,
                created_by=user,
            )
    except IntegrityError:
        existing = get_school_academic_year(school_id)
        if existing is None:
            raise
        return existing
