from ninja import Schema
from pydantic import Field, field_validator


class AdminClassOut(Schema):
    class_id: int
    class_code: str
    class_name: str
    sequence: int  # read-only: derived from the next-class chain
    next_class_id: int | None
    next_class_name: str | None
    open_for_enrolment: bool
    is_active: bool
    in_use_count: int = 0

    @staticmethod
    def resolve_next_class_id(obj) -> int | None:
        return int(obj.next_class_id_id) if obj.next_class_id_id is not None else None

    @staticmethod
    def resolve_next_class_name(obj) -> str | None:
        return obj.next_class_id.class_name if obj.next_class_id_id else None

    @staticmethod
    def resolve_in_use_count(obj) -> int:
        return getattr(obj, "in_use_count", 0)


class AdminClassCreateIn(Schema):
    class_code: str = Field(min_length=1, max_length=4)
    class_name: str = Field(min_length=1, max_length=20)
    next_class_id: int | None = None
    open_for_enrolment: bool = True

    @field_validator("class_code", "class_name")
    @classmethod
    def _strip_non_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class AdminClassPatchIn(Schema):
    class_code: str | None = Field(default=None, min_length=1, max_length=4)
    class_name: str | None = Field(default=None, min_length=1, max_length=20)
    next_class_id: int | None = None
    open_for_enrolment: bool | None = None
    is_active: bool | None = None

    @field_validator("class_code", "class_name")
    @classmethod
    def _strip_non_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v
