from django.db import transaction

from sessionops.exceptions import ConflictError, NotFound, ValidationError
from sessionops.models import Class, SchoolClass, User
from sessionops.services.catalog.order import recompute_sequences
from sessionops.services.catalog.rules import validate_next_class


def _get_next(next_class_id: int | None) -> Class | None:
    if next_class_id is None:
        return None
    try:
        return Class.objects.get(pk=next_class_id, removed=False)
    except Class.DoesNotExist:
        raise ValidationError(f"Class {next_class_id} does not exist.")


@transaction.atomic
def create_class(payload, user: User) -> Class:
    from sessionops.services.children.enroll import get_foundation_program_id

    code = payload.class_code.strip()
    if Class.objects.filter(class_code=code).exists():
        raise ConflictError(f"Class code '{code}' already exists.")
    next_cls = _get_next(payload.next_class_id)
    validate_next_class(None, next_cls)
    cls = Class.objects.create(
        class_code=code,
        class_name=payload.class_name.strip(),
        next_class_id=next_cls,
        open_for_enrolment=payload.open_for_enrolment,
        program_id_id=get_foundation_program_id(),
        created_by=user,
    )
    # Order is derived from the next-class chain, never typed by an admin.
    recompute_sequences()
    cls.refresh_from_db(fields=["sequence"])
    return cls


@transaction.atomic
def update_class(class_id: int, payload, user: User) -> Class:
    try:
        cls = Class.objects.select_for_update().get(pk=class_id, removed=False)
    except Class.DoesNotExist:
        raise NotFound(f"Class {class_id} not found.")

    fields = payload.model_dump(exclude_unset=True)

    if "class_code" in fields:
        code = fields["class_code"].strip()
        if Class.objects.filter(class_code=code).exclude(pk=cls.pk).exists():
            raise ConflictError(f"Class code '{code}' already exists.")
        cls.class_code = code
    if "class_name" in fields:
        cls.class_name = fields["class_name"].strip()
    if "open_for_enrolment" in fields:
        cls.open_for_enrolment = fields["open_for_enrolment"]
    if "next_class_id" in fields:
        next_cls = _get_next(fields["next_class_id"])
        validate_next_class(cls, next_cls)
        cls.next_class_id = next_cls
    if fields.get("is_active") is False and cls.is_active:
        _assert_can_deactivate(cls)
        cls.is_active = False
    elif fields.get("is_active") is True:
        cls.is_active = True

    cls.updated_by = user
    cls.save()
    recompute_sequences()
    cls.refresh_from_db(fields=["sequence"])
    return cls


def _assert_can_deactivate(cls: Class) -> None:
    in_use = SchoolClass.objects.filter(class_id=cls.pk, is_active=True, removed=False).count()
    if in_use:
        raise ConflictError(
            f"{cls.class_name} is used by {in_use} school class(es) and cannot be deactivated."
        )
    pointing = list(
        Class.objects.filter(next_class_id=cls, is_active=True, removed=False).values_list(
            "class_name", flat=True
        )
    )
    if pointing:
        raise ConflictError(
            f"{cls.class_name} is the next class of {', '.join(pointing)}; change that first."
        )
