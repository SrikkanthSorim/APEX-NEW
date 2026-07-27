"""Typed shapes for the OpenRewrite-based test inventory and test-execution
results.

These mirror the JSON produced by the ``rewrite-test-inventory`` Java CLI
tool (see ``app/infrastructure/testing/rewrite_inventory_tool.py``) and the
parsed Surefire/JaCoCo XML reports. The persisted per-job
``unit-test-report.json`` itself stays a plain camelCase dict, matching every
other stage report in this codebase (connect/discovery/migration-config/
migration reports are all built as raw dicts, not dataclasses) -- these
dataclasses exist purely to give the analysis/selection/coverage logic a
typed, convenient in-memory structure to work with before it gets flattened
into that dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# -- production/test class inventory (from the OpenRewrite LST scan) ------- #

# Business-logic-bearing class types, per the spec's BL coverage definition:
# Services, business/domain logic, validators, utilities containing logic,
# converters containing logic. DTO-only, entity-only, configuration, and
# generated/interface-only classes are excluded.
BUSINESS_LOGIC_CLASS_TYPES = frozenset({"SERVICE", "VALIDATOR", "CONVERTER", "UTILITY", "DOMAIN"})

# Classes eligible for automatic test generation (Step 4's "initially
# prioritize" list, plus CONTROLLER/ENTITY/OTHER once they have at least one
# non-trivial method -- see class_selector._has_testable_method). The Java
# classifier's OTHER bucket in particular catches real, testable classes
# (a SOAP client, a scheduled/cron job) whose methods just happen to have no
# branches; excluding the whole bucket by class_type alone was too strict.
#
# Permanently excluded regardless of method content: DTO (data-only by
# definition), CONFIGURATION/REPOSITORY_INTERFACE/INTERFACE_ONLY (no method
# bodies to test), CONSTANTS/EXCEPTION (nothing meaningful to assert), and
# MAIN_APPLICATION (a Spring Boot entrypoint's only statement is
# SpringApplication.run(...) -- there is no real behavior to test without
# inventing one, which the generation prompt explicitly forbids).
GENERATION_ELIGIBLE_CLASS_TYPES = frozenset(
    {"SERVICE", "VALIDATOR", "CONVERTER", "UTILITY", "DOMAIN", "CONTROLLER", "ENTITY", "OTHER"}
)


@dataclass(frozen=True)
class MethodInventoryEntry:
    name: str
    visibility: str
    return_type: str
    parameters: list[dict[str, str]]
    branch_count: int
    throws_exceptions: bool

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "MethodInventoryEntry":
        return MethodInventoryEntry(
            name=data.get("name", ""),
            visibility=data.get("visibility", "package-private"),
            return_type=data.get("returnType", "void"),
            parameters=list(data.get("parameters") or []),
            branch_count=int(data.get("branchCount") or 0),
            throws_exceptions=bool(data.get("throwsExceptions")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "visibility": self.visibility,
            "returnType": self.return_type,
            "parameters": self.parameters,
            "branchCount": self.branch_count,
            "throwsExceptions": self.throws_exceptions,
        }


@dataclass(frozen=True)
class ClassInventoryEntry:
    class_name: str
    package_name: str
    source_path: str
    class_type: str
    is_interface: bool
    is_abstract: bool
    annotations: list[str]
    dependencies: list[str]
    methods: list[MethodInventoryEntry]
    existing_test_class: str | None
    existing_test_count: int

    @property
    def fully_qualified_name(self) -> str:
        return f"{self.package_name}.{self.class_name}" if self.package_name else self.class_name

    @property
    def is_business_logic(self) -> bool:
        return self.class_type in BUSINESS_LOGIC_CLASS_TYPES

    @property
    def is_generation_eligible(self) -> bool:
        # classType alone (ABSTRACT_CLASS/INTERFACE_ONLY/REPOSITORY_INTERFACE
        # are never in GENERATION_ELIGIBLE_CLASS_TYPES) already excludes
        # these -- the explicit checks here are defense-in-depth so a
        # classifier bug can never again offer an interface/abstract class
        # up for generation (see: ITodoService incorrectly generating tests).
        return (
            self.class_type in GENERATION_ELIGIBLE_CLASS_TYPES
            and not self.is_interface
            and not self.is_abstract
        )

    @property
    def has_branches_or_exceptions(self) -> bool:
        return any(m.branch_count > 0 or m.throws_exceptions for m in self.methods)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ClassInventoryEntry":
        return ClassInventoryEntry(
            class_name=data.get("className", ""),
            package_name=data.get("packageName", ""),
            source_path=data.get("sourcePath", ""),
            class_type=data.get("classType", "OTHER"),
            is_interface=bool(data.get("isInterface")),
            is_abstract=bool(data.get("isAbstract")),
            annotations=list(data.get("annotations") or []),
            dependencies=list(data.get("dependencies") or []),
            methods=[MethodInventoryEntry.from_dict(m) for m in (data.get("methods") or [])],
            existing_test_class=data.get("existingTestClass"),
            existing_test_count=int(data.get("existingTestCount") or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "className": self.class_name,
            "packageName": self.package_name,
            "sourcePath": self.source_path,
            "classType": self.class_type,
            "isInterface": self.is_interface,
            "isAbstract": self.is_abstract,
            "annotations": self.annotations,
            "dependencies": self.dependencies,
            "methods": [m.to_dict() for m in self.methods],
            "existingTestClass": self.existing_test_class,
            "existingTestCount": self.existing_test_count,
        }


@dataclass(frozen=True)
class TestClassInventoryEntry:
    class_name: str
    package_name: str
    source_path: str
    test_framework: str
    test_methods: list[dict[str, Any]]
    mockito_used: bool
    tested_class_name_guess: str

    @property
    def active_test_count(self) -> int:
        return sum(1 for m in self.test_methods if not m.get("disabled"))

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "TestClassInventoryEntry":
        return TestClassInventoryEntry(
            class_name=data.get("className", ""),
            package_name=data.get("packageName", ""),
            source_path=data.get("sourcePath", ""),
            test_framework=data.get("testFramework", "UNKNOWN"),
            test_methods=list(data.get("testMethods") or []),
            mockito_used=bool(data.get("mockitoUsed")),
            tested_class_name_guess=data.get("testedClassNameGuess", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "className": self.class_name,
            "packageName": self.package_name,
            "sourcePath": self.source_path,
            "testFramework": self.test_framework,
            "testMethods": self.test_methods,
            "mockitoUsed": self.mockito_used,
            "testedClassNameGuess": self.tested_class_name_guess,
        }


@dataclass(frozen=True)
class ProjectInventory:
    project_dir: str
    production_file_count: int
    test_file_count: int
    production_classes: list[ClassInventoryEntry]
    test_classes: list[TestClassInventoryEntry]
    parse_errors: list[str] = field(default_factory=list)

    @property
    def existing_test_file_count(self) -> int:
        return len(self.test_classes)

    @property
    def existing_test_case_count(self) -> int:
        return sum(c.active_test_count for c in self.test_classes)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ProjectInventory":
        return ProjectInventory(
            project_dir=data.get("projectDir", ""),
            production_file_count=int(data.get("productionFileCount") or 0),
            test_file_count=int(data.get("testFileCount") or 0),
            production_classes=[ClassInventoryEntry.from_dict(c) for c in (data.get("productionClasses") or [])],
            test_classes=[TestClassInventoryEntry.from_dict(c) for c in (data.get("testClasses") or [])],
            parse_errors=list(data.get("parseErrors") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "projectDir": self.project_dir,
            "productionFileCount": self.production_file_count,
            "testFileCount": self.test_file_count,
            "productionClasses": [c.to_dict() for c in self.production_classes],
            "testClasses": [c.to_dict() for c in self.test_classes],
            "parseErrors": self.parse_errors,
        }


# -- test execution (Surefire) ---------------------------------------------- #


@dataclass(frozen=True)
class TestFailureEntry:
    test_class: str
    test_method: str
    failure_type: str  # "FAILURE" | "ERROR"
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "testClass": self.test_class,
            "testMethod": self.test_method,
            "type": self.failure_type,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TestExecutionSummary:
    available: bool
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    failures: list[TestFailureEntry] = field(default_factory=list)
    reason: str | None = None  # populated when available is False


# -- coverage (JaCoCo) -------------------------------------------------------- #


@dataclass(frozen=True)
class CoverageMetrics:
    available: bool
    instruction_coverage_pct: float | None = None
    line_coverage_pct: float | None = None
    branch_coverage_pct: float | None = None
    method_coverage_pct: float | None = None
    class_coverage_pct: float | None = None
    lines_covered: int = 0
    lines_missed: int = 0
    reason: str | None = None  # populated when available is False

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "instruction_coverage_pct": self.instruction_coverage_pct,
            "line_coverage_pct": self.line_coverage_pct,
            "branch_coverage_pct": self.branch_coverage_pct,
            "method_coverage_pct": self.method_coverage_pct,
            "class_coverage_pct": self.class_coverage_pct,
            "lines_covered": self.lines_covered,
            "lines_missed": self.lines_missed,
            "reason": self.reason,
        }
