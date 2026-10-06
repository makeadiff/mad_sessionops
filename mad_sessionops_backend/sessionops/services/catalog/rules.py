"""F-M10-1: class catalog rules — the single place enrolment/next-class policy lives.

Policy is data (Class.open_for_enrolment / next_class_id), edited by admins in
Admin → Classes; these functions only enforce it.
"""

from sessionops.exceptions import ValidationError
from sessionops.models import Class


def assert_class_open_for_enrolment(cls: Class, *, allow_prior: bool = False) -> None:
    """Raise ValidationError if `cls` is closed for new enrolment.

    Applies wherever a class is newly bound: adding it to a school, enrolling a
    child into it, or moving a child into it by editing. `allow_prior` lets
    reactivation restore a child into the class they were already in — a
    restoration of their own history, not a new assignment. Year progression
    moves children into closed classes without calling this.
    """
    if cls.open_for_enrolment or allow_prior:
        return
    raise ValidationError(
        f"{cls.class_name} cannot be assigned directly. It is closed for new enrolment "
        "and only reachable via year-end progression."
    )


def validate_next_class(cls: Class | None, next_cls: Class | None) -> None:
    """Next class must be a different, active class and must not create a cycle.

    `cls` is None when creating a new class (it can't be part of a cycle yet).
    """
    if next_cls is None:
        return
    if cls is not None and next_cls.pk == cls.pk:
        raise ValidationError("A class cannot be its own next class.")
    if not next_cls.is_active or next_cls.removed:
        raise ValidationError(f"{next_cls.class_name} is inactive and cannot be a next class.")
    if cls is None:
        return
    # Walk the chain from the proposed next class; reaching `cls` means a cycle.
    seen: set[int] = set()
    node: Class | None = next_cls
    while node is not None and node.pk not in seen:
        if node.pk == cls.pk:
            raise ValidationError(
                f"Setting {next_cls.class_name} as the next class of {cls.class_name} "
                "would create a cycle."
            )
        seen.add(node.pk)
        node = node.next_class_id
