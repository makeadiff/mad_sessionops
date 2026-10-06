"""
Models package for sessionops.

=============================================================================
MODEL ORGANIZATION BEST PRACTICES
=============================================================================

This package organizes models into separate files for:
1. Readability: Each model file is focused and manageable
2. Maintainability: Easy to find and modify specific models
3. Git History: Changes to one model don't affect other files
4. Team Collaboration: Reduces merge conflicts

Structure:
    models/
    ├── __init__.py      <- You are here (exports all models)
    ├── user.py          <- User identity model
    └── user_auth.py     <- Authentication credentials model

Usage:
    # Import from package (recommended)
    from sessionops.models import User, UserAuth

    # Or import from specific module
    from sessionops.models.user import User

=============================================================================
"""

# =============================================================================
# EXPORT ALL MODELS
# =============================================================================
# By importing models here, they become available when importing from
# sessionops.models directly. This is the Pythonic way to create a public API
# for your models package.
#
# Django also needs this for migrations to work correctly. When Django
# looks for models in the 'sessionops' app, it checks sessionops.models.__init__.py.
# =============================================================================

# M2 models
from sessionops.models.academic_year import AcademicYear, SchoolAcademicYear
from sessionops.models.base import SoftDeleteBaseModel, SoftDeleteManager
from sessionops.models.child import (
    BatchChild,
    Child,
    ChildClass,
    ChildClassSection,
    ChildProgram,
    ChildRemovalLog,
)
from sessionops.models.child_subject import ChildSubject
from sessionops.models.class_section import ClassSection
from sessionops.models.class_section_subject import ClassSectionSubject

# M9 models
from sessionops.models.export_log import EXPORT_TYPES, ExportLog
from sessionops.models.grade_class import Class, SchoolClass
from sessionops.models.partner import Partner

# M3 models
from sessionops.models.partner_worknode import PartnerWorknode
from sessionops.models.password_reset_token import PasswordResetToken
from sessionops.models.program import Program

# M10 models
from sessionops.models.progression import (
    FROZEN_STATUSES,
    ProgressionRowLog,
    ProgressionRun,
    SchoolProgression,
)

# M8a models
from sessionops.models.realtime_sync_log import (
    ACTIONS_TAKEN,
    EVENT_TYPES,
    SYNC_STATUSES,
    SYNC_TYPES,
    RealtimeSyncLog,
)
from sessionops.models.school_holiday import HOLIDAY_REASONS, SchoolHoliday
from sessionops.models.school_volunteer import SchoolVolunteer

# M4 models
from sessionops.models.session_details import SchoolSessionDetails
from sessionops.models.slot import Slot
from sessionops.models.slot_class_section import SlotClassSection
from sessionops.models.slot_class_section_volunteer import SlotClassSectionVolunteer
from sessionops.models.subject import Subject
from sessionops.models.sync_run import SyncRun
from sessionops.models.user import User
from sessionops.models.user_auth import UserAuth

__all__ = [
    "SchoolSessionDetails",
    "SchoolHoliday",
    "HOLIDAY_REASONS",
    "SoftDeleteBaseModel",
    "SoftDeleteManager",
    "User",
    "UserAuth",
    "PasswordResetToken",
    "Partner",
    "SyncRun",
    # M3
    "PartnerWorknode",
    "Subject",
    "SchoolVolunteer",
    "Slot",
    "ClassSectionSubject",
    "ChildSubject",
    "SlotClassSection",
    "SlotClassSectionVolunteer",
    # M2
    "AcademicYear",
    "SchoolAcademicYear",
    "Program",
    "Class",
    "SchoolClass",
    "ClassSection",
    "Child",
    "ChildClass",
    "ChildClassSection",
    "BatchChild",
    "ChildProgram",
    "ChildRemovalLog",
    # M8a
    "RealtimeSyncLog",
    "SYNC_TYPES",
    "EVENT_TYPES",
    "SYNC_STATUSES",
    "ACTIONS_TAKEN",
    # M10
    "ProgressionRun",
    "SchoolProgression",
    "ProgressionRowLog",
    "FROZEN_STATUSES",
    # M9
    "ExportLog",
    "EXPORT_TYPES",
]
