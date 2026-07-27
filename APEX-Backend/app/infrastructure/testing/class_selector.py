"""Selects which production classes are eligible for automatic test
generation (Step 4 of the spec): prioritize Service/Validator/Converter/
logic-bearing Utility/Domain classes, then Controller/uncategorized-"Other"/
Entity classes that have at least one method beyond a plain getter/setter, all
with no existing test coverage; skip interfaces, abstract classes, and
DTO/Configuration/Repository-interface/Constants/Exception/main-application
classes (genuinely no testable body/behavior -- see
``GENERATION_ELIGIBLE_CLASS_TYPES``). Pure Python, no subprocess -- operates
on the already-parsed ``ProjectInventory``, using the OpenRewrite-derived
``is_interface``/``is_abstract``/``classType`` fields (never a name-pattern
guess of its own) to decide.
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.domain.models.unit_test_report import (
    GENERATION_ELIGIBLE_CLASS_TYPES,
    ClassInventoryEntry,
    ProjectInventory,
)

logger = logging.getLogger(__name__)

# Lower number = higher priority, per the spec's "initially prioritize" order.
# CONTROLLER/OTHER/ENTITY are real generation candidates too (see
# GENERATION_ELIGIBLE_CLASS_TYPES) but rank behind the classic business-logic
# types so a capped batch (unit_test_generation_max_classes) still favors
# services/validators/converters/utilities/domain classes first.
_TYPE_PRIORITY = {
    "SERVICE": 0,
    "VALIDATOR": 1,
    "CONVERTER": 2,
    "UTILITY": 3,
    "DOMAIN": 4,
    "CONTROLLER": 5,
    "OTHER": 6,
    "ENTITY": 7,
}

REASON_INTERFACE = "INTERFACE"
REASON_ABSTRACT_CLASS = "ABSTRACT_CLASS"
REASON_ALREADY_HAS_TESTS = "ALREADY_HAS_TESTS"
REASON_NO_MEANINGFUL_METHODS = "NO_MEANINGFUL_METHODS"
REASON_MAX_CLASSES_REACHED = "MAX_CLASSES_REACHED"


def _is_trivial_accessor(method) -> bool:
    """Same shape the Java classifier itself uses to spot a plain getter/setter --
    mirrored here (rather than requiring branches) so a real, testable
    straight-line method (e.g. a SOAP client call or a cron job's run method,
    which often have zero branches) isn't excluded just for lacking an `if`."""
    name = method.name or ""
    is_getter = (name.startswith("get") or name.startswith("is")) and not method.parameters
    is_setter = name.startswith("set") and len(method.parameters) == 1
    return method.branch_count == 0 and not method.throws_exceptions and (is_getter or is_setter)


def _has_testable_method(entry: ClassInventoryEntry) -> bool:
    """A class is worth generating tests for once it has at least one method
    that isn't a pure getter/setter -- e.g. a plain JPA entity with only
    field accessors still correctly yields no candidates here, while an
    entity/controller/otherwise-uncategorized class with real behavior does."""
    return any(not _is_trivial_accessor(m) for m in entry.methods)


def _skip_reason(entry: ClassInventoryEntry) -> str | None:
    """Return why ``entry`` is not a generation candidate, or ``None`` if it is."""
    if entry.is_interface:
        return REASON_INTERFACE
    if entry.is_abstract:
        return REASON_ABSTRACT_CLASS
    if entry.class_type not in GENERATION_ELIGIBLE_CLASS_TYPES:
        return f"CLASS_TYPE_{entry.class_type}"
    if entry.existing_test_count > 0:
        return REASON_ALREADY_HAS_TESTS
    if not entry.methods or not _has_testable_method(entry):
        return REASON_NO_MEANINGFUL_METHODS
    return None


def select_classes_for_generation(
    inventory: ProjectInventory, max_classes: int | None = None
) -> list[ClassInventoryEntry]:
    """Return production classes that need generated tests, most important first.

    Every excluded class is logged with a real reason (interface, abstract,
    wrong class type, already tested, no meaningful methods, or bounded out
    by ``max_classes``) -- never silently dropped.
    """
    limit = max_classes if max_classes is not None else settings.unit_test_generation_max_classes

    candidates: list[ClassInventoryEntry] = []
    for entry in inventory.production_classes:
        reason = _skip_reason(entry)
        if reason is None:
            candidates.append(entry)
        else:
            logger.info("Unit test generation skipped | class=%s | reason=%s", entry.class_name, reason)

    candidates.sort(key=lambda entry: (_TYPE_PRIORITY.get(entry.class_type, 99), -_method_weight(entry)))

    # `limit is None` means unbounded (the default) -- every eligible class
    # gets generation. `candidates[None:]` below would otherwise be the whole
    # list again (Python slice semantics), which would wrongly log every
    # selected class as bounded out, so this is handled explicitly.
    if limit is None:
        for entry in candidates:
            logger.info("Class selected for generation | class=%s | classType=%s", entry.class_name, entry.class_type)
        return candidates

    selected = candidates[:limit]
    for entry in selected:
        logger.info("Class selected for generation | class=%s | classType=%s", entry.class_name, entry.class_type)
    for entry in candidates[limit:]:
        logger.info(
            "Unit test generation skipped | class=%s | reason=%s", entry.class_name, REASON_MAX_CLASSES_REACHED
        )
    return selected


def _method_weight(entry: ClassInventoryEntry) -> int:
    """More branches/exceptions -> more valuable to test first."""
    return sum(m.branch_count + (1 if m.throws_exceptions else 0) for m in entry.methods)
