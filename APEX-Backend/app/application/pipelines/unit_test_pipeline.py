"""Unit Test pipeline: thin orchestration exposed to the controller.

Mirrors ``MigrationExecutionPipeline``'s shape (validate/delegate/shape) --
no business logic lives here, only wiring between the use cases, the
persisted report, and the job's workspace paths.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.application.services.unit_test_html_report import render_html_report
from app.application.services.status_service import MigrationReportStore
from app.application.use_cases.analyze_unit_tests import AnalyzeUnitTestsUseCase
from app.application.use_cases.generate_unit_tests import (
    GenerateUnitTestsUseCase,
    GenerationResult,
    apply_generation_result,
)
from app.application.use_cases.run_unit_tests import RunUnitTestsUseCase
from app.core.exceptions import (
    UnitTestReportNotFoundError,
    UnitTestUnsupportedProjectError,
    UnitTestWorkspaceNotFoundError,
)
from app.domain.enums.unit_test_status import GENERATION_STATUS_NOT_STARTED, UnitTestStatus
from app.domain.models.unit_test_report import ProjectInventory
from app.infrastructure.persistence.job_repository import JobRepository
from app.infrastructure.workspace.workspace_paths import WorkspacePaths

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UnitTestPipeline:
    def __init__(
        self,
        job_repository: JobRepository | None = None,
        analyze_use_case: AnalyzeUnitTestsUseCase | None = None,
        generate_use_case: GenerateUnitTestsUseCase | None = None,
        run_use_case: RunUnitTestsUseCase | None = None,
    ) -> None:
        self._job_repository = job_repository or JobRepository()
        self._analyze = analyze_use_case or AnalyzeUnitTestsUseCase(self._job_repository)
        self._generate = generate_use_case or GenerateUnitTestsUseCase()
        self._run = run_use_case or RunUnitTestsUseCase(self._job_repository)

    # -- endpoints ------------------------------------------------------------- #

    def analyze(self, job_id: str) -> dict[str, Any]:
        paths = WorkspacePaths(job_id)
        project_dir, source_label = self._resolve_readable_project_dir(paths)
        build_tool = self._read_build_tool(job_id)
        return self._analyze.execute(job_id, project_dir, source_label, build_tool)

    def generate(self, job_id: str) -> dict[str, Any]:
        paths = WorkspacePaths(job_id)
        project_dir = self._require_migrated_repo(paths)
        build_tool = self._read_build_tool(job_id)
        if build_tool not in ("MAVEN", "GRADLE"):
            raise UnitTestUnsupportedProjectError()

        analysis = self._analyze.execute(job_id, project_dir, "migrated-repo", build_tool)
        inventory = ProjectInventory.from_dict(analysis.get("inventory") or {})

        discovery = self._job_repository.read_discovery_report(job_id) or {}
        migration = self._read_migration_report(job_id)
        java_version = migration.get("effectiveTargetJavaVersion") or migration.get("targetJavaVersion") or ""
        target_major = self._parse_major(java_version)

        self._mark_generation_in_progress(job_id)

        def _on_class_done(partial: GenerationResult, class_name: str, completed: int, total: int) -> None:
            report = self._job_repository.read_unit_test_report(job_id) or {"jobId": job_id}
            report = apply_generation_result(report, partial)
            report["status"] = UnitTestStatus.TEST_GENERATION_IN_PROGRESS.value
            report["generationProgress"] = {
                "currentClass": class_name,
                "completedClasses": completed,
                "totalClasses": total,
            }
            report["updatedAt"] = _now()
            self._job_repository.save_unit_test_report(job_id, report)

        result = self._generate.execute(
            job_id, project_dir, inventory,
            java_version=java_version,
            spring_boot_version=discovery.get("springBootVersion"),
            build_tool=build_tool,
            target_major=target_major,
            on_class_done=_on_class_done,
        )

        report = self._job_repository.read_unit_test_report(job_id) or {}
        report = apply_generation_result(report, result)
        report.pop("generationProgress", None)
        self._job_repository.save_unit_test_report(job_id, report)
        summary = report.get("summary") or {}
        logger.info(
            "Unit test report persisted | job_id=%s | generationStatus=%s | newTestFiles=%s | generatedTestCases=%s",
            job_id, result.generation_status, summary.get("newTestFiles"), summary.get("generatedTestCases"),
        )
        return report

    def run(self, job_id: str) -> dict[str, Any]:
        paths = WorkspacePaths(job_id)
        project_dir = self._require_migrated_repo(paths)
        build_tool = self._read_build_tool(job_id)
        if build_tool not in ("MAVEN", "GRADLE"):
            raise UnitTestUnsupportedProjectError()

        report = self._job_repository.read_unit_test_report(job_id)
        inventory = ProjectInventory.from_dict((report or {}).get("inventory") or {})
        if not inventory.production_classes and not inventory.test_classes:
            analysis = self._analyze.execute(job_id, project_dir, "migrated-repo", build_tool)
            inventory = ProjectInventory.from_dict(analysis.get("inventory") or {})

        migration = self._read_migration_report(job_id)
        target_major = self._parse_major(
            migration.get("effectiveTargetJavaVersion") or migration.get("targetJavaVersion") or ""
        )
        return self._run.execute(job_id, project_dir, inventory, target_major, build_tool=build_tool)

    def rerun(self, job_id: str) -> dict[str, Any]:
        """Re-execute existing + already-generated tests. Never regenerates
        or creates duplicate files -- only ``generate()`` writes new files.
        """
        paths = WorkspacePaths(job_id)
        project_dir = self._require_migrated_repo(paths)
        build_tool = self._read_build_tool(job_id)
        if build_tool not in ("MAVEN", "GRADLE"):
            raise UnitTestUnsupportedProjectError()

        analysis = self._analyze.execute(job_id, project_dir, "migrated-repo", build_tool)
        inventory = ProjectInventory.from_dict(analysis.get("inventory") or {})
        migration = self._read_migration_report(job_id)
        target_major = self._parse_major(
            migration.get("effectiveTargetJavaVersion") or migration.get("targetJavaVersion") or ""
        )
        return self._run.execute(job_id, project_dir, inventory, target_major, build_tool=build_tool)

    def get_status(self, job_id: str) -> dict[str, Any]:
        report = self._require_report(job_id)
        return {
            "jobId": job_id,
            "status": report.get("status"),
            "summary": report.get("summary"),
            "updatedAt": report.get("updatedAt"),
        }

    def get_report(self, job_id: str) -> dict[str, Any]:
        return self._require_report(job_id)

    def render_html_report(self, job_id: str) -> str:
        report = self._require_report(job_id)
        return render_html_report(job_id, report)

    def get_generated_files(self, job_id: str) -> dict[str, Any]:
        report = self._require_report(job_id)
        return {"jobId": job_id, "generatedFiles": report.get("generatedFiles") or []}

    # -- helpers --------------------------------------------------------------- #

    def _mark_generation_in_progress(self, job_id: str) -> None:
        report = self._job_repository.read_unit_test_report(job_id) or {"jobId": job_id}
        report.update(
            status=UnitTestStatus.TEST_GENERATION_IN_PROGRESS.value,
            updatedAt=_now(),
            completedAt=None,
            generationStatus=GENERATION_STATUS_NOT_STARTED,
            llmProvider=report.get("llmProvider") or "groq",
        )
        self._job_repository.save_unit_test_report(job_id, report)

    def _require_report(self, job_id: str) -> dict[str, Any]:
        report = self._job_repository.read_unit_test_report(job_id)
        if not report:
            raise UnitTestReportNotFoundError()
        return report

    @staticmethod
    def _resolve_readable_project_dir(paths: WorkspacePaths) -> tuple[Any, str]:
        if paths.migrated_repo_dir.is_dir():
            return paths.migrated_repo_dir, "migrated-repo"
        if paths.original_repo_dir.is_dir():
            return paths.original_repo_dir, "original-repo"
        raise UnitTestWorkspaceNotFoundError()

    @staticmethod
    def _require_migrated_repo(paths: WorkspacePaths) -> Any:
        if not paths.migrated_repo_dir.is_dir():
            raise UnitTestWorkspaceNotFoundError(
                "No migrated repository workspace found for this job. Start migration first."
            )
        return paths.migrated_repo_dir

    @staticmethod
    def _read_migration_report(job_id: str) -> dict[str, Any]:
        return MigrationReportStore(WorkspacePaths(job_id)).read() or {}

    def _read_build_tool(self, job_id: str) -> str:
        migration = self._read_migration_report(job_id)
        if migration.get("buildTool"):
            return str(migration["buildTool"]).upper()
        discovery = self._job_repository.read_discovery_report(job_id) or {}
        return str(discovery.get("buildTool") or "").upper()

    @staticmethod
    def _parse_major(version: str) -> int | None:
        digits = "".join(ch for ch in (version or "") if ch.isdigit())
        return int(digits) if digits else None
