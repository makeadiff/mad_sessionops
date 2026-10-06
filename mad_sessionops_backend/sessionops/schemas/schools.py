from datetime import date, datetime
from typing import Optional

from ninja import Schema

from sessionops.schemas.auth import ScopeWarningSchema


class SchoolListItemSchema(Schema):
    partner_id: int
    name: str
    initials: str
    city: Optional[str] = None
    contact_person_name: Optional[str] = None
    contact_phone: Optional[str] = None
    co_name: Optional[str] = None
    setup_status: str  # 'configured' | 'partial' | 'not_configured'
    children_count: int = 0
    volunteers_count: int = 0
    assignments_count: int = 0
    classes_count: int = 0
    academic_year_label: Optional[str] = None
    updated_at: Optional[datetime] = None


class SchoolSummarySchema(Schema):
    total_schools: int
    fully_configured: int
    children_enrolled: int
    active_volunteers: int
    academic_year: Optional[str] = None


class SchoolListResponseSchema(Schema):
    schools: list[SchoolListItemSchema]
    summary: SchoolSummarySchema
    scope_warning: Optional[ScopeWarningSchema] = None
    # F-M10-5: in-scope schools hidden because they are being progressed
    progressing_count: int = 0


class ChoOut(Schema):
    user_id: int
    user_display_name: str


class SchoolDetailSchema(Schema):
    partner_id: int
    partner_name: str
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[int] = None
    school_type: Optional[str] = None
    partner_affiliation_type: Optional[str] = None
    poc_name: Optional[str] = None
    poc_email: Optional[str] = None
    poc_designation: Optional[str] = None
    poc_contact: Optional[str] = None
    mou_sign_date: Optional[date] = None
    mou_start_date: Optional[date] = None
    mou_end_date: Optional[date] = None
    mou_url: Optional[str] = None
    co_id: Optional[int] = None
    co_name: Optional[str] = None
    chos: list[ChoOut] = []
    synced_at: Optional[datetime] = None
    configuration_status: str = "awaiting_setup"
    children_count: int = 0
    confirmed_child_count: Optional[int] = None
    classes_count: int = 0
    volunteers_count: int = 0
    assignments_count: int = 0
    academic_year_label: Optional[str] = None
