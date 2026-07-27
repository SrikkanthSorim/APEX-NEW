"""Analyze Unit Tests use case.

Runs the OpenRewrite LST inventory scan over a project directory and decides
whether existing tests are sufficient or generation is required (Steps 2-4).
Called (a) immediately after Discovery's clone, read-only against
``original-repo``, and (b) again against ``migrated-repo`` before generation,
since migration may have changed the source. Never raises -- any failure is
recorded on the unit-test report's own status so it can never break the
Discovery or Migration flow that calls it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.exceptions import UnitTestError
from app.domain.enums.unit_test_status import UnitTestStatus
from app.infrastructure.persistence.job_repository import JobRepository
from app.infrastructure.testing.rewrite_inventory_tool import RewriteInventoryTool

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalyzeUnitTestsUseCase:
    def __init__(
        self,
        job_repository: JobRepository | None = None,
        inventory_tool: RewriteInventoryTool | None = None,
    ) -> None:
        self._job_repository = job_repository or JobRepository()
        self._inventory_tool = inventory_tool or RewriteInventoryTool()

    def execute(self, job_id: str, project_dir: Path, source_label: str, build_tool: str) -> dict[str, Any]:
        existing = self._job_repository.read_unit_test_report(job_id) or {}
        started_at = existing.get("startedAt") or _now()
        base = self._base_report(job_id, build_tool, source_label, started_at)

        if build_tool not in ("MAVEN", "GRADLE"):
            return self._fail(
                job_id, existing, base,
                "Automatic unit test generation/execution currently supports single-module "
                "Maven or Gradle projects only.",
            )

        if not self._inventory_tool.is_available():
            return self._fail(
                job_id, existing, base,
                "The OpenRewrite test-inventory tool is not available. Build it with "
                "`mvn -f tools/rewrite-test-inventory/pom.xml package`.",
            )

        try:
            inventory = self._inventory_tool.scan(project_dir)
        except UnitTestError as exc:
            return self._fail(job_id, existing, base, exc.message)
        except Exception:  # noqa: BLE001 - report cleanly, never raise into the caller's flow
            logger.exception("Unit test inventory scan failed unexpectedly for job %s", job_id)
            return self._fail(job_id, existing, base, "Unit test inventory scan failed unexpectedly.")

        status = (
            UnitTestStatus.NO_TESTS_FOUND
            if inventory.existing_test_file_count == 0
            else UnitTestStatus.TEST_ANALYSIS_COMPLETED
        )

        prior_summary = existing.get("summary") or {}
        generated_test_cases = int(prior_summary.get("generatedTestCases") or 0)
        report = {
            **base,
            "status": status.value,
            "inventory": inventory.to_dict(),
            "summary": {
                "totalSourceFiles": inventory.production_file_count,
                "existingTestFiles": inventory.existing_test_file_count,
                "newTestFiles": int(prior_summary.get("newTestFiles") or 0),
                "existingTestCases": inventory.existing_test_case_count,
                "generatedTestCases": generated_test_cases,
                "totalTestCases": inventory.existing_test_case_count + generated_test_cases,
                "passedTests": int(prior_summary.get("passedTests") or 0),
                "failedTests": int(prior_summary.get("failedTests") or 0),
                "skippedTests": int(prior_summary.get("skippedTests") or 0),
            },
            "generatedFiles": existing.get("generatedFiles") or [],
            "failures": existing.get("failures") or [],
            "coverage": existing.get("coverage") or {
                "businessLogicLineCoverage": None,
                "jacocoLineCoverage": None,
                "branchCoverage": None,
            },
        }
        self._job_repository.save_unit_test_report(job_id, report)
        logger.info(
            "Unit test analysis completed | job_id=%s | source_files=%s | existing_test_files=%s | "
            "existing_test_cases=%s | source=%s",
            job_id, inventory.production_file_count, inventory.existing_test_file_count,
            inventory.existing_test_case_count, source_label,
        )
        return report

    # -- helpers --------------------------------------------------------------- #

    @staticmethod
    def _base_report(job_id: str, build_tool: str, source_label: str, started_at: str) -> dict[str, Any]:
        return {
            "jobId": job_id,
            "buildTool": build_tool,
            "sourceLabel": source_label,
            "startedAt": started_at,
            "updatedAt": _now(),
            "completedAt": None,
            "llmModel": None,
            "llmProvider": None,
            "errorSummary": None,
        }

    def _fail(self, job_id: str, existing: dict[str, Any], base: dict[str, Any], message: str) -> dict[str, Any]:
        report = {**existing, **base, "status": UnitTestStatus.FAILED.value, "errorSummary": message}
        self._job_repository.save_unit_test_report(job_id, report)
        logger.warning("Unit test analysis failed | job_id=%s | reason=%s", job_id, message)
        return report
