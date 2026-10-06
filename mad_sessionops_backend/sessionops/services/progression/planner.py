"""F-M10-6: the progression planner — the single source of truth for what a run does.

`build_plans(school_ids, marks)` loads everything for all the given schools in a
FIXED number of queries and returns one `SchoolPlan` per school — each moving
from its own active year to the year after it (services/progression/target.py):
blockers, warnings, every move (classes, sections, children, volunteers), every
row id to archive, and the preview counts. Precheck and preview read the plan;
F-M10-7 execution applies exactly this plan inside the school's transaction, so
the preview can never disagree with the run.

Mapping rules (M10.md Part 1):
- SchoolClass: copy every active offering of the current school-year; add any
  class that promoted children need and the school doesn't offer.
- ClassSection: copy every active section (incl. empty; incl. legacy rows with no
  school-year) — same names, no class link, new school-year.
- Child: to catalog next_class, or stay when next_class is null; or graduate when
  marked (class-level or individually).
- SchoolVolunteer: carried to the new school-year.
- Slots / slot-classes / assignments / class-section subjects / child subjects /
  session: archived only.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Q

from sessionops.exceptions import ValidationError
from sessionops.models import (
    AcademicYear,
    BatchChild,
    Child,
    ChildClass,
    ChildClassSection,
    ChildSubject,
    Class,
    ClassSection,
    ClassSectionSubject,
    Partner,
    SchoolAcademicYear,
    SchoolClass,
    SchoolSessionDetails,
    SchoolVolunteer,
    Slot,
    SlotClassSection,
    SlotClassSectionVolunteer,
)
from sessionops.services.progression.target import (
    active_year,
    label_start,
    next_label,
    years_by_start,
)

# ── Codes ──────────────────────────────────────────────────────────────────────

BLOCKER_MESSAGES = {
    "NOT_CONVERTED": "The school is not converted.",
    "NO_NEXT_YEAR": "{label} does not exist yet. Create it in Admin → Academic Years first.",
    "NO_ACTIVE_SCHOOL_YEAR": "The school has no active academic year.",
    "CHILD_CLASS_CONFLICT": "{n} active child(ren) have no class, several classes, or a class outside the current year.",
    "CHILD_SECTION_CONFLICT": "{n} active child(ren) are in more than one section.",
    "NEXT_CLASS_INACTIVE": "The next class of {classes} is inactive. Fix it in Admin → Classes.",
    "ALREADY_IN_RUN": "The school is already in an unfinished progression run.",
    "TARGET_NOT_LATER": "The school's year changed since the run started (now {current}).",
}

WARNING_MESSAGES = {
    "NO_NEXT_CLASS": "{n} child(ren) in {classes} have no next class and will stay in that class.",
    "CHILD_NO_SECTION": "{n} child(ren) have no section and will stay without one.",
    "CLASS_CLOSED_TARGET": "Children will move into {classes}, which is closed for new enrolment (allowed for progression).",
    "LEGACY_NO_SCHOOL_YEAR": "{n} older row(s) have no academic year link; they are treated as this year's.",
    "ACTIVE_TIMETABLE": "{slots} slot(s), {slot_classes} slot-class(es) and {assignments} assignment(s) will be archived; the timetable must be rebuilt.",
    "ACTIVE_SESSION": "The term dates will be archived; new ones must be set.",
    "STILL_BEHIND": "After this run the school is still {n} year(s) behind {active}; progress it again to catch up.",
}

# Archive buckets, in the order execution archives them (db_table names).
ARCHIVE_TABLES = (
    "school_class",
    "class_section",
    "child_class",
    "child_class_section",
    "batch_child",
    "school_volunteer",
    "slot",
    "slot_class_section",
    "slot_class_section_volunteer",
    "class_section_subject",
    "child_subject",
    "school_session_details",
)


# ── Plan structures ────────────────────────────────────────────────────────────


@dataclass
class ClassCopy:
    class_id: int
    class_name: str
    source_school_class_id: int | None  # None = added for promoted children


@dataclass
class SectionCopy:
    source_class_section_id: int
    section_name: str
    section_display_name: str | None


@dataclass
class ChildMove:
    child_id: int
    from_class_id: int
    to_class_id: int | None  # None = graduate
    source_child_class_id: int
    source_section_id: int | None  # the section the child is in (mapped at execution)


@dataclass
class SchoolPlan:
    school_id: int
    school_name: str
    current_year_label: str | None
    from_school_academic_year_id: int | None
    to_year: AcademicYear | None = None  # the year after the school's own
    blockers: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    school_classes: list[ClassCopy] = field(default_factory=list)
    sections: list[SectionCopy] = field(default_factory=list)
    children: list[ChildMove] = field(default_factory=list)
    volunteer_ids: list[int] = field(default_factory=list)  # SchoolVolunteer rows to carry
    archive: dict[str, list[int]] = field(default_factory=lambda: {t: [] for t in ARCHIVE_TABLES})
    counts: dict = field(default_factory=dict)

    @property
    def to_year_label(self) -> str | None:
        if self.to_year is not None:
            return self.to_year.label
        return next_label(self.current_year_label) if self.current_year_label else None

    @property
    def status(self) -> str:
        if self.blockers:
            return "blocked"
        if self.warnings:
            return "warning"
        return "ready"


@dataclass
class Marks:
    graduate_class_ids: set[int] = field(default_factory=set)
    graduate_child_ids: set[int] = field(default_factory=set)


def _blocker(plan: SchoolPlan, code: str, **fmt) -> None:
    plan.blockers.append({"code": code, "message": BLOCKER_MESSAGES[code].format(**fmt), **fmt})


def _warning(plan: SchoolPlan, code: str, **fmt) -> None:
    plan.warnings.append({"code": code, "message": WARNING_MESSAGES[code].format(**fmt), **fmt})


def _names(class_ids, catalog: dict[int, Class]) -> str:
    return ", ".join(sorted({catalog[c].class_name for c in class_ids if c in catalog}))


# ── Builder ────────────────────────────────────────────────────────────────────
#
# build_plans loads everything for all schools up front (_load_current,
# _load_archive: a fixed number of queries), then plans each school with small
# pure steps (_plan_year, _plan_children, _plan_structure, _plan_warnings,
# _plan_counts) that only read the loaded data.


@dataclass
class _Loaded:
    """Everything build_plans needs, loaded once for all schools."""

    partners: dict[int, Partner]
    catalog: dict[int, Class]
    says: dict[int, SchoolAcademicYear]
    years: dict[int, AcademicYear]
    active: AcademicYear | None
    school_classes: defaultdict[int, list[SchoolClass]]
    sc_by_id: dict[int, SchoolClass]
    sections: defaultdict[int, list[ClassSection]]
    legacy_rows: defaultdict[int, int]
    children: defaultdict[int, list[Child]]
    child_classes: defaultdict[int, list[ChildClass]]
    child_sections: defaultdict[int, list[ChildClassSection]]
    batch: defaultdict[int, list[int]]
    volunteers: defaultdict[int, list[SchoolVolunteer]]
    # Archive-only rows, by school.
    slots: defaultdict[int, list[int]] = field(default_factory=lambda: defaultdict(list))
    slot_classes: defaultdict[int, list[int]] = field(default_factory=lambda: defaultdict(list))
    assignments: defaultdict[int, list[int]] = field(default_factory=lambda: defaultdict(list))
    section_subjects: defaultdict[int, list[int]] = field(default_factory=lambda: defaultdict(list))
    child_subjects: defaultdict[int, list[int]] = field(default_factory=lambda: defaultdict(list))
    sessions: defaultdict[int, list[int]] = field(default_factory=lambda: defaultdict(list))


def _group(rows, key) -> defaultdict:
    out: defaultdict = defaultdict(list)
    for row in rows:
        out[key(row)].append(row)
    return out


def _group_ids(pairs) -> defaultdict[int, list[int]]:
    """[(row_id, school_id), ...] → {school_id: [row_id, ...]}."""
    out: defaultdict[int, list[int]] = defaultdict(list)
    for row_id, school_id in pairs:
        out[school_id].append(row_id)
    return out


def _load_current(ids: list[int]) -> _Loaded:
    """Partners, catalog, years, and each school's current-year structure + children."""
    says = {
        s.school_id: s
        for s in SchoolAcademicYear.objects.filter(
            school_id__in=ids, is_active=True, removed=False
        ).select_related("academic_year_id")
    }
    say_ids = [s.pk for s in says.values()]

    school_classes = _group(
        SchoolClass.objects.filter(
            school_academic_year_id__in=say_ids, is_active=True, removed=False
        ),
        lambda sc: sc.school_id,
    )
    sections = _group(
        ClassSection.objects.filter(
            Q(school_academic_year_id__in=say_ids) | Q(school_academic_year_id__isnull=True),
            school_id__in=ids,
            is_active=True,
            removed=False,
        ).order_by("section_display_name", "section_name", "class_section_id"),
        lambda cs: cs.school_id,
    )
    legacy_rows: defaultdict[int, int] = defaultdict(int)
    for rows in sections.values():
        for cs in rows:
            if cs.school_academic_year_id_id is None:
                legacy_rows[cs.school_id] += 1

    children = _group(
        Child.objects.filter(school_id__in=ids, is_active=True, removed=False).order_by("child_id"),
        lambda c: c.school_id,
    )
    child_ids = [c.pk for rows in children.values() for c in rows]
    live = {"child_id__in": child_ids, "is_active": True, "removed": False}

    return _Loaded(
        partners={p.partner_id: p for p in Partner.objects.filter(partner_id__in=ids)},
        catalog={c.class_id: c for c in Class.objects.filter(removed=False)},
        says=says,
        years=years_by_start(),
        active=active_year(),
        school_classes=school_classes,
        sc_by_id={sc.pk: sc for rows in school_classes.values() for sc in rows},
        sections=sections,
        legacy_rows=legacy_rows,
        children=children,
        child_classes=_group(ChildClass.objects.filter(**live), lambda cc: cc.child_id_id),
        child_sections=_group(
            ChildClassSection.objects.filter(**live), lambda ccs: ccs.child_id_id
        ),
        batch=_group_ids(BatchChild.objects.filter(**live).values_list("pk", "child_id")),
        volunteers=_group(
            SchoolVolunteer.objects.filter(school_id__in=ids, is_active=True, removed=False),
            lambda sv: sv.school_id,
        ),
    )


def _load_archive(d: _Loaded) -> None:
    """Timetable, subjects and session rows of the current year (archive only)."""
    say_ids = [s.pk for s in d.says.values()]
    live = {"is_active": True, "removed": False}
    d.slots = _group_ids(
        Slot.objects.filter(school_academic_year_id__in=say_ids, **live).values_list(
            "slot_id", "school_id"
        )
    )
    d.slot_classes = _group_ids(
        SlotClassSection.objects.filter(
            slot_id__in=[s for rows in d.slots.values() for s in rows], **live
        ).values_list("slot_class_section_id", "slot_id__school_id")
    )
    d.assignments = _group_ids(
        SlotClassSectionVolunteer.objects.filter(
            slot_class_section_id__in=[s for rows in d.slot_classes.values() for s in rows],
            **live,
        ).values_list(
            "slot_class_section_volunteer_id", "slot_class_section_id__slot_id__school_id"
        )
    )
    d.section_subjects = _group_ids(
        ClassSectionSubject.objects.filter(
            class_section_id__in=[cs.pk for rows in d.sections.values() for cs in rows], **live
        ).values_list("class_section_subject_id", "class_section_id__school_id")
    )
    d.child_subjects = _group_ids(
        ChildSubject.objects.filter(
            class_section_subject_id__in=[c for rows in d.section_subjects.values() for c in rows],
            **live,
        ).values_list("child_subject_id", "class_section_subject_id__class_section_id__school_id")
    )
    d.sessions = _group_ids(
        SchoolSessionDetails.objects.filter(school_academic_year__in=say_ids, **live).values_list(
            "session_id", "school_id"
        )
    )


@dataclass
class _ChildTally:
    conflict: int = 0
    section_conflict: int = 0
    no_section: int = 0
    graduating: int = 0
    staying: defaultdict[int, int] = field(default_factory=lambda: defaultdict(int))
    moving: defaultdict[tuple[int, int], int] = field(default_factory=lambda: defaultdict(int))
    inactive_next: set[int] = field(default_factory=set)
    closed_targets: set[int] = field(default_factory=set)
    target_class_ids: set[int] = field(default_factory=set)


def _plan_year(
    plan: SchoolPlan, say: SchoolAcademicYear, d: _Loaded, pinned: AcademicYear | None
) -> None:
    """Target = the year after the school's own (or the year pinned at Start)."""
    current = say.academic_year_id.label
    current_start = label_start(current)
    target = pinned or d.years.get(current_start + 1)
    plan.to_year = target
    if target is None:
        _blocker(plan, "NO_NEXT_YEAR", label=next_label(current))
    elif label_start(target.label) != current_start + 1:
        _blocker(plan, "TARGET_NOT_LATER", current=current)
    elif d.active is not None and label_start(target.label) < label_start(d.active.label):
        _warning(
            plan,
            "STILL_BEHIND",
            n=label_start(d.active.label) - label_start(target.label),
            active=d.active.label,
        )


def _next_class(from_class_id: int, catalog: dict[int, Class]) -> Class | None:
    # Resolve through the loaded catalog by id (not the lazy FK) so the query
    # count stays fixed however many classes are involved.
    cls = catalog.get(from_class_id)
    return catalog.get(cls.next_class_id_id) if cls and cls.next_class_id_id else None


def _plan_child(plan: SchoolPlan, child: Child, d: _Loaded, marks: Marks, t: _ChildTally) -> None:
    cc_rows = d.child_classes.get(child.pk, [])
    if len(cc_rows) != 1 or cc_rows[0].school_class_id_id not in d.sc_by_id:
        t.conflict += 1
        return
    cc = cc_rows[0]
    from_class_id = d.sc_by_id[cc.school_class_id_id].class_id_id
    secs = d.child_sections.get(child.pk, [])
    if len(secs) > 1:
        t.section_conflict += 1
        return
    source_section = secs[0].class_section_id_id if secs else None

    graduate = child.pk in marks.graduate_child_ids or from_class_id in marks.graduate_class_ids
    to_class_id: int | None
    if graduate:
        to_class_id = None
        t.graduating += 1
    else:
        nxt = _next_class(from_class_id, d.catalog)
        if nxt is None:
            to_class_id = from_class_id
            t.staying[from_class_id] += 1
        else:
            if not nxt.is_active:
                t.inactive_next.add(from_class_id)
            to_class_id = nxt.pk
            t.moving[(from_class_id, to_class_id)] += 1
            if not nxt.open_for_enrolment:
                t.closed_targets.add(to_class_id)
        t.target_class_ids.add(to_class_id)
        if source_section is None:
            t.no_section += 1

    plan.children.append(
        ChildMove(
            child_id=child.pk,
            from_class_id=from_class_id,
            to_class_id=to_class_id,
            source_child_class_id=cc.pk,
            source_section_id=source_section,
        )
    )
    if not graduate:
        # Graduates' links are retired by retire_child at execution (like a
        # deactivation), so they are not in the archive lists.
        plan.archive["child_class"].append(cc.pk)
        plan.archive["child_class_section"].extend(s.pk for s in secs)
        plan.archive["batch_child"].extend(d.batch.get(child.pk, []))


def _plan_children(plan: SchoolPlan, d: _Loaded, marks: Marks) -> _ChildTally:
    t = _ChildTally()
    for child in d.children.get(plan.school_id, []):
        _plan_child(plan, child, d, marks, t)
    if t.conflict:
        _blocker(plan, "CHILD_CLASS_CONFLICT", n=t.conflict)
    if t.section_conflict:
        _blocker(plan, "CHILD_SECTION_CONFLICT", n=t.section_conflict)
    if t.inactive_next:
        _blocker(plan, "NEXT_CLASS_INACTIVE", classes=_names(t.inactive_next, d.catalog))
    return t


def _plan_structure(plan: SchoolPlan, d: _Loaded, t: _ChildTally) -> tuple[int, list[int]]:
    """Classes (copy offerings + add what promoted children need), sections, volunteers
    and the archive lists. Returns (offered count, added class ids)."""
    school_id, catalog = plan.school_id, d.catalog
    offered: set[int] = set()
    for sc in d.school_classes.get(school_id, []):
        offered.add(sc.class_id_id)
        plan.school_classes.append(
            ClassCopy(sc.class_id_id, catalog[sc.class_id_id].class_name, sc.pk)
        )
        plan.archive["school_class"].append(sc.pk)
    added = sorted(
        (c for c in t.target_class_ids if c not in offered),
        key=lambda c: (catalog[c].sequence, catalog[c].class_code),
    )
    for class_id in added:
        plan.school_classes.append(ClassCopy(class_id, catalog[class_id].class_name, None))

    # Sections: all active, incl. empty and legacy.
    for cs in d.sections.get(school_id, []):
        plan.sections.append(SectionCopy(cs.pk, cs.section_name, cs.section_display_name))
        plan.archive["class_section"].append(cs.pk)

    svs = d.volunteers.get(school_id, [])
    plan.volunteer_ids = [sv.pk for sv in svs]
    plan.archive["school_volunteer"] = [sv.pk for sv in svs]
    d.legacy_rows[school_id] += sum(1 for sv in svs if sv.school_academic_year_id_id is None)
    plan.archive["slot"] = d.slots.get(school_id, [])
    plan.archive["slot_class_section"] = d.slot_classes.get(school_id, [])
    plan.archive["slot_class_section_volunteer"] = d.assignments.get(school_id, [])
    plan.archive["class_section_subject"] = d.section_subjects.get(school_id, [])
    plan.archive["child_subject"] = d.child_subjects.get(school_id, [])
    plan.archive["school_session_details"] = d.sessions.get(school_id, [])
    return len(offered), added


def _plan_warnings(plan: SchoolPlan, d: _Loaded, t: _ChildTally) -> None:
    if t.staying:
        _warning(
            plan,
            "NO_NEXT_CLASS",
            n=sum(t.staying.values()),
            classes=_names(t.staying, d.catalog),
        )
    if t.no_section:
        _warning(plan, "CHILD_NO_SECTION", n=t.no_section)
    if t.closed_targets:
        _warning(plan, "CLASS_CLOSED_TARGET", classes=_names(t.closed_targets, d.catalog))
    if d.legacy_rows.get(plan.school_id):
        _warning(plan, "LEGACY_NO_SCHOOL_YEAR", n=d.legacy_rows[plan.school_id])
    if plan.archive["slot"] or plan.archive["slot_class_section"]:
        _warning(
            plan,
            "ACTIVE_TIMETABLE",
            slots=len(plan.archive["slot"]),
            slot_classes=len(plan.archive["slot_class_section"]),
            assignments=len(plan.archive["slot_class_section_volunteer"]),
        )
    if plan.archive["school_session_details"]:
        _warning(plan, "ACTIVE_SESSION")


def _plan_counts(
    plan: SchoolPlan, catalog: dict[int, Class], t: _ChildTally, offered: int, added: list[int]
) -> None:
    plan.counts = {
        "school_classes_copied": offered,
        "school_classes_added": [catalog[c].class_name for c in added],
        "sections_copied": len(plan.sections),
        "children_moving": [
            {"from": catalog[f].class_name, "to": catalog[to].class_name, "n": n}
            for (f, to), n in sorted(
                t.moving.items(),
                key=lambda kv: (catalog[kv[0][0]].sequence, kv[0][1]),
            )
        ],
        "children_staying": [
            {"class": catalog[c].class_name, "n": n}
            for c, n in sorted(t.staying.items(), key=lambda kv: catalog[kv[0]].sequence)
        ],
        "children_graduating": t.graduating,
        "volunteers_carried": len(plan.volunteer_ids),
        "archive_counts": {table: len(v) for table, v in plan.archive.items()},
    }


def build_plans(
    school_ids: list[int],
    marks: dict[int, Marks] | None = None,
    *,
    frozen_ids: set[int] | None = None,
    targets: dict[int, AcademicYear] | None = None,
) -> dict[int, SchoolPlan]:
    """One SchoolPlan per school id, in a fixed number of queries (independent of
    school or child count). `frozen_ids` = schools in an unfinished run (caller
    supplies it so execution can plan its own already-queued school). `targets`
    pins a school's target (execution uses the year fixed when the run started);
    otherwise each school targets the year after its own."""
    marks = marks or {}
    frozen_ids = frozen_ids or set()
    targets = targets or {}
    ids = list(dict.fromkeys(school_ids))
    if not ids:
        return {}

    d = _load_current(ids)
    _load_archive(d)

    plans: dict[int, SchoolPlan] = {}
    for school_id in ids:
        partner = d.partners.get(school_id)
        say = d.says.get(school_id)
        plan = SchoolPlan(
            school_id=school_id,
            school_name=partner.partner_name if partner else f"School {school_id}",
            current_year_label=say.academic_year_id.label if say else None,
            from_school_academic_year_id=say.pk if say else None,
        )
        plans[school_id] = plan

        # School-level blockers.
        if partner is None or not partner.converted:
            _blocker(plan, "NOT_CONVERTED")
        if school_id in frozen_ids:
            _blocker(plan, "ALREADY_IN_RUN")
        if say is None:
            _blocker(plan, "NO_ACTIVE_SCHOOL_YEAR")
            continue
        _plan_year(plan, say, d, targets.get(school_id))

        tally = _plan_children(plan, d, marks.get(school_id, Marks()))
        offered, added = _plan_structure(plan, d, tally)
        _plan_warnings(plan, d, tally)
        _plan_counts(plan, d.catalog, tally, offered, added)
    return plans


# ── Mark validation ────────────────────────────────────────────────────────────


def validate_marks(school_id: int, marks: Marks) -> None:
    """Graduation marks must refer to this school's active children / catalog classes."""
    if marks.graduate_child_ids:
        found = set(
            Child.objects.filter(
                pk__in=marks.graduate_child_ids,
                school_id=school_id,
                is_active=True,
                removed=False,
            ).values_list("pk", flat=True)
        )
        unknown = sorted(marks.graduate_child_ids - found)
        if unknown:
            raise ValidationError(
                f"Children {unknown} are not active children of school {school_id}."
            )
    if marks.graduate_class_ids:
        found = set(
            Class.objects.filter(pk__in=marks.graduate_class_ids, removed=False).values_list(
                "pk", flat=True
            )
        )
        unknown = sorted(marks.graduate_class_ids - found)
        if unknown:
            raise ValidationError(f"Classes {unknown} do not exist.")
