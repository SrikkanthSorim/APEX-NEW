"""Run Unit Tests use case (Steps 7 and 9 of the spec).

Executes the complete test suite (existing + any accepted generated tests)
with JaCoCo instrumentation, parses the real Surefire/JaCoCo XML output (never
text-scanning for "BUILD SUCCESS"), and persists the final counts/coverage.
A failing test never raises -- it is recorded as ``COMPLETED_WITH_ISSUES`` so
migration success is never conditioned on test outcomes.

Stale test-results/JaCoCo output from a *previous* run (``target/...`` for
Maven, ``build/...`` for Gradle -- see ``build_tool_paths``) is deleted before
invoking the build tool, so a report can only ever reflect *this* run --
otherwise a completely failed invocation could silently be "graded" using
leftover output from an earlier successful run.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.domain.enums.unit_test_status import (
    COVERAGE_STATUS_GENERATED,
    COVERAGE_STATUS_INVALID,
    COVERAGE_STATUS_MISSING,
    TEST_EXECUTION_STATUS_COMPILATION_FAILED,
    TEST_EXECUTION_STATUS_FAILED,
    TEST_EXECUTION_STATUS_NO_TESTS_EXECUTED,
    TEST_EXECUTION_STATUS_PASSED,
    TEST_EXECUTION_STATUS_TIMEOUT,
    UnitTestStatus,
)
from app.domain.models.build_result import BUILD_STATUS_TIMEOUT, BuildResult
from app.domain.models.unit_test_report import CoverageMetrics, ProjectInventory, TestExecutionSummary
from app.infrastructure.persistence.job_repository import JobRepository
from app.infrastructure.testing.build_tool_paths import stale_report_dirs
from app.infrastructure.testing.gradle_test_runner import GradleTestRunner
from app.infrastructure.testing.jacoco_report_parser import parse_jacoco_report
from app.infrastructure.testing.maven_test_runner import MavenTestRunner
from app.infrastructure.testing.surefire_report_parser import parse_surefire_reports

logger = logging.getLogger(__name__)

# Failure "type" values written by the *generation* phase (GenerateUnitTestsUseCase)
# -- kept apart from execution-phase failures (surefire "FAILURE"/"ERROR",
# see surefire_report_parser.py) so this use case's own report write below
# only ever replaces the execution-phase failures it just produced, instead
# of discarding the (still-relevant, and otherwise unrecoverable) reasons a
# class was never generated in the first place.
_GENERATION_FAILURE_TYPES = frozenset({
    "GENERATION_FAILED", "GENERATION_TIMEOUT", "GENERATION_RATE_LIMITED",
    "VALIDATION_FAILED", "COMPILATION_FAILED", "GENERATION_ERROR", "WRITE_FAILED",
})

# generationStatus values (see unit_test_status.py) where generation did not
# fully complete for every candidate class -- surfaced as COMPLETED_WITH_ISSUES
# even when every test that *did* run passed, so the Result page/report
# reflects that automatic generation was cut short rather than looking like
# an unqualified clean pass.
_INCOMPLETE_GENERATION_STATUSES = frozenset({
    "TIME_BUDGET_EXCEEDED", "SKIPPED_RATE_LIMITED",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunUnitTestsUseCase:
    def __init__(
        self,
        job_repository: JobRepository | None = None,
        maven_runner: MavenTestRunner | None = None,
        gradle_runner: GradleTestRunner | None = None,
    ) -> None:
        self._job_repository = job_repository or JobRepository()
        self._maven_runner = maven_runner or MavenTestRunner()
        self._gradle_runner = gradle_runner or GradleTestRunner()

    def execute(
        self,
        job_id: str,
        project_dir: Path,
        inventory: ProjectInventory,
        target_major: int | None = None,
        build_tool: str = "MAVEN",
    ) -> dict[str, Any]:
        existing = self._job_repository.read_unit_test_report(job_id) or {}
        runner = self._gradle_runner if (build_tool or "").upper() == "GRADLE" else self._maven_runner

        self._clean_stale_reports(project_dir, build_tool)
        build_result = runner.run_suite_with_coverage(project_dir, target_major)
        execution = parse_surefire_reports(project_dir, build_tool)

        business_logic_names = {
            entry.fully_qualified_name for entry in inventory.production_classes if entry.is_business_logic
        }
        overall_coverage, bl_coverage = parse_jacoco_report(project_dir, business_logic_names, build_tool)

        test_execution_status = self._determine_test_execution_status(build_result, execution)
        coverage_status = self._determine_coverage_status(overall_coverage.available, overall_coverage.reason)
        status = self._overall_status(test_execution_status, existing.get("generationStatus"))

        self._log_results(job_id, test_execution_status, execution, build_result)
        self._log_coverage(job_id, coverage_status, overall_coverage, bl_coverage)

        summary = dict(existing.get("summary") or {})
        if execution.available:
            summary.update(
                passedTests=execution.passed,
                failedTests=execution.failed + execution.errors,
                skippedTests=execution.skipped,
            )

        jacoco_coverage = overall_coverage.line_coverage_pct if overall_coverage.available else None
        business_logic_coverage = bl_coverage.line_coverage_pct if bl_coverage.available else None

        # Preserve generation-phase failure reasons (why a class was never
        # generated) -- only the execution-phase failures below are replaced
        # with this run's fresh results; generation failures don't change
        # between runs/reruns, since only generate() ever writes new files.
        generation_failures = [
            f for f in (existing.get("failures") or []) if f.get("type") in _GENERATION_FAILURE_TYPES
        ]

        report = {
            **existing,
            "jobId": job_id,
            "status": status.value,
            "updatedAt": _now(),
            "completedAt": _now(),
            "summary": summary,
            "failures": generation_failures + [f.to_dict() for f in execution.failures],
            "coverage": {
                "businessLogicLineCoverage": business_logic_coverage,
                "jacocoLineCoverage": jacoco_coverage,
                "branchCoverage": overall_coverage.branch_coverage_pct if overall_coverage.available else None,
                "businessLogicCoverageAvailable": bl_coverage.available,
                "businessLogicCoverageReason": bl_coverage.reason,
                "jacocoCoverageAvailable": overall_coverage.available,
                "jacocoCoverageReason": overall_coverage.reason,
            },
            "buildStatus": build_result.status,
            "buildSafeSummary": build_result.safe_summary,
            "testExecutionAvailable": execution.available,
            "testExecutionReason": execution.reason,
            # -- exact fields required by the Result page's granular status
            #    contract -- additive; the nested `coverage{}`/`summary{}`
            #    fields above are unchanged for existing consumers. --
            "testExecutionStatus": test_execution_status,
            "coverageStatus": coverage_status,
            "jacocoCoverage": jacoco_coverage,
            "businessLogicCoverage": business_logic_coverage,
        }
        self._job_repository.save_unit_test_report(job_id, report)
        logger.info(
            "Unit test report persisted | job_id=%s | status=%s | newTestFiles=%s | generatedTestCases=%s",
            job_id, status.value, summary.get("newTestFiles"), summary.get("generatedTestCases"),
        )
        return report

    # -- stale-report cleanup -------------------------------------------------- #

    @staticmethod
    def _clean_stale_reports(project_dir: Path, build_tool: str) -> None:
        for path in stale_report_dirs(project_dir, build_tool):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)

    # -- status determination --------------------------------------------------- #

    @staticmethod
    def _determine_test_execution_status(build_result: BuildResult, execution: TestExecutionSummary) -> str:
        if build_result.status == BUILD_STATUS_TIMEOUT:
            return TEST_EXECUTION_STATUS_TIMEOUT
        if not execution.available:
            # No Surefire report at all: either the build genuinely failed to
            # compile (a real compiler error), or there simply were no test
            # classes to run.
            if not build_result.success:
                return TEST_EXECUTION_STATUS_COMPILATION_FAILED
            return TEST_EXECUTION_STATUS_NO_TESTS_EXECUTED
        if execution.total == 0:
            return TEST_EXECUTION_STATUS_NO_TESTS_EXECUTED
        if execution.failed > 0 or execution.errors > 0:
            return TEST_EXECUTION_STATUS_FAILED
        return TEST_EXECUTION_STATUS_PASSED

    @staticmethod
    def _determine_coverage_status(available: bool, reason: str | None) -> str:
        if available:
            return COVERAGE_STATUS_GENERATED
        if reason and "not found" in reason.lower():
            return COVERAGE_STATUS_MISSING
        return COVERAGE_STATUS_INVALID

    @staticmethod
    def _overall_status(test_execution_status: str, generation_status: str | None = None) -> UnitTestStatus:
        if test_execution_status == TEST_EXECUTION_STATUS_TIMEOUT:
            return UnitTestStatus.TEST_EXECUTION_TIMEOUT
        if test_execution_status == TEST_EXECUTION_STATUS_COMPILATION_FAILED:
            return UnitTestStatus.TEST_COMPILATION_FAILED
        if test_execution_status == TEST_EXECUTION_STATUS_NO_TESTS_EXECUTED:
            return UnitTestStatus.TEST_NOT_EXECUTED
        if test_execution_status == TEST_EXECUTION_STATUS_FAILED:
            return UnitTestStatus.COMPLETED_WITH_ISSUES
        if generation_status in _INCOMPLETE_GENERATION_STATUSES:
            # Every test that *did* run passed, but automatic generation was
            # cut short before every candidate class was attempted -- not a
            # clean, unqualified completion. SKIPPED_RATE_LIMITED is kept for
            # older persisted reports; new runs use rate-limit fallback.
            return UnitTestStatus.COMPLETED_WITH_ISSUES
        return UnitTestStatus.COMPLETED

    # -- logging ------------------------------------------------------------ #

    @staticmethod
    def _log_results(
        job_id: str, test_execution_status: str, execution: TestExecutionSummary, build_result: BuildResult
    ) -> None:
        logger.info(
            "Unit test execution completed | job_id=%s | total=%s | passed=%s | failed=%s | skipped=%s | "
            "status=%s | duration_ms=%s",
            job_id, execution.total, execution.passed, execution.failed + execution.errors,
            execution.skipped, test_execution_status, build_result.duration_ms,
        )
        for failure in execution.failures:
            logger.info(
                "Unit test failure | job_id=%s | class=%s | method=%s | type=%s | reason=%s",
                job_id, failure.test_class, failure.test_method, failure.failure_type, failure.reason,
            )
        if test_execution_status == TEST_EXECUTION_STATUS_COMPILATION_FAILED:
            logger.warning(
                "Unit test compilation failed | job_id=%s | reason=%s",
                job_id, build_result.safe_summary or "See build log for details.",
            )

    @staticmethod
    def _log_coverage(
        job_id: str, coverage_status: str, overall_coverage: CoverageMetrics, bl_coverage: CoverageMetrics
    ) -> None:
        logger.info(
            "JaCoCo processing completed | job_id=%s | status=%s | line_coverage=%s",
            job_id, coverage_status, overall_coverage.line_coverage_pct if coverage_status == COVERAGE_STATUS_GENERATED else None,
        )
        if coverage_status == COVERAGE_STATUS_GENERATED:
            logger.info(
                "JaCoCo report generated | job_id=%s | jacoco_line_coverage=%s | bl_line_coverage=%s",
                job_id, overall_coverage.line_coverage_pct,
                bl_coverage.line_coverage_pct if bl_coverage.available else None,
            )
        else:
            logger.warning(
                "JaCoCo report unavailable | job_id=%s | status=%s | reason=%s",
                job_id, coverage_status, overall_coverage.reason,
            )
