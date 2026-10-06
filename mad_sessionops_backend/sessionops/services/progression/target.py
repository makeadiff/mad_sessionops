"""Which academic year each school moves into (2026-10-05: per school, not per run).

Every school moves ONE year ahead of its own active school-year: 2025-26 → 2026-27,
2026-27 → 2027-28, in the same run. Schools that aren't selected stay where they
are and never block anyone. No skipping: a school two years behind is progressed
twice. The next year must already exist (Admin → Academic Years); otherwise the
school is blocked with NO_NEXT_YEAR.

The platform's single active year (R8) follows the newest year any school has
been moved into: Start flips it when a selected school's target is later than
the active year. Undo never flips it back.

Labels are "YYYY-YYYY" (schema-validated), compared by their first year.
"""

from sessionops.models import AcademicYear


def label_start(label: str) -> int:
    return int(label.split("-", 1)[0])


def next_label(label: str) -> str:
    start = label_start(label) + 1
    return f"{start}-{start + 1}"


def years_by_start() -> dict[int, AcademicYear]:
    """All non-removed years keyed by their first year (labels are unique)."""
    return {label_start(y.label): y for y in AcademicYear.objects.filter(removed=False)}


def active_year() -> AcademicYear | None:
    return AcademicYear.objects.filter(is_active=True, removed=False).first()
