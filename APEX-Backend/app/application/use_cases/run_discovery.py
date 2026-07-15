"""Run Discovery use case.

Responsibilities:
  * Validate that the connect report exists (Connect step completed).
  * Prepare the job workspace and clone the repo into ``original-repo``.
  * Analyze the cloned project (read-only) via the ProjectAnalyzer.
  * Save ``discovery-report.json``.
  * Return a clean discovery summary.

Explicitly NOT done here: migration, OpenRewrite, Maven/Gradle builds, pushing
to GitHub, or any modification of the cloned repository.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.exceptions import ConnectReportNotFoundError, UnsupportedProjectError
from app.infrastructure.analyzers.project_analyzer import ProjectAnalysis, ProjectAnalyzer
from app.infrastructure.analyzers.spring_boot_eligibility import (
    SpringBootEligibility,
    compute_eligibility,
)
from app.infrastructure.git.repository_cloner import RepositoryCloner
from app.infrastructure.persistence.job_repository import JobRepository
from app.infrastructure.workspace.workspace_manager import WorkspaceManager
from app.infrastructure.workspace.workspace_paths import WorkspacePaths

logger = logging.getLogger(__name__)

STATUS_COMPLETED = "DISCOVERY_COMPLETED"
NEXT_STEP = "STRATEGY"


@dataclass(frozen=True)
class DiscoveryOutcome:
    """What the use case returns: the ready-to-send response plus the report."""

    response: dict[str, Any]
    report: dict[str, Any]


class RunDiscoveryUseCase:
    def __init__(
        self,
        job_repository: JobRepository | None = None,
        cloner: RepositoryCloner | None = None,
        analyzer: ProjectAnalyzer | None = None,
    ) -> None:
        self._job_repository = job_repository or JobRepository()
        self._cloner = cloner or RepositoryCloner()
        self._analyzer = analyzer or ProjectAnalyzer()

    def execute(self, job_id: str, request_token: str | None = None) -> DiscoveryOutcome:
        # 1. Connect report must exist.
        connect = self._job_repository.read_connect_report(job_id)
        if not connect:
            raise ConnectReportNotFoundError()

        repo_url = connect.get("repoUrl", "")
        owner = connect.get("owner", "")
        repo_name = connect.get("repoName", "")
        visibility = connect.get("repoVisibility", "PUBLIC")

        token = (
            (request_token or "").strip()
            or (connect.get("githubToken") or "").strip()
            or (settings.github_token or "").strip()
            or None
        )

        logger.info("Discovery started for job %s (%s)", job_id, repo_url)

        # 2. Prepare workspace + clone into original-repo.
        paths = WorkspacePaths(job_id)
        workspace = WorkspaceManager(paths)
        workspace.ensure_job_dirs()
        workspace.prepare_original_repo_target()

        logger.info("Cloning repository into workspace for job %s ...", job_id)
        self._cloner.clone(
            repo_url,
            paths.original_repo_dir,
            token=token,
            log_path=paths.discovery_log_path,
        )
        logger.info("Clone finished for job %s. Analyzing project ...", job_id)

        # 3. Analyze the cloned project (read-only).
        analysis = self._analyzer.analyze(paths.original_repo_dir)
        if not analysis.is_supported:
            logger.info("Discovery for job %s: unsupported project (no Maven/Gradle).", job_id)
            raise UnsupportedProjectError()

        eligibility = compute_eligibility(
            build_tool_supported=analysis.is_supported,
            build_tool=analysis.build_tool,
            project_type=analysis.project_type,
            spring_framework_version=analysis.spring_framework_version,
            spring_boot_version=analysis.spring_boot_version,
            spring_boot_signal=analysis.spring_boot_signal,
            entrypoint_found=analysis.spring_entry_class is not None,
        )

        logger.info(
            "Discovery completed for job %s: buildTool=%s javaVersion=%s springBoot=%s "
            "type=%s multiModule=%s dependencies=%d frontend=%s "
            "springDetected=%s springBootDetected=%s conversionEligible=%s upgradeEligible=%s",
            job_id,
            analysis.build_tool,
            analysis.current_java_version,
            analysis.spring_boot_version,
            analysis.project_type,
            analysis.multi_module,
            analysis.dependency_count,
            analysis.frontend.type if analysis.frontend.detected else "none",
            eligibility.spring_detected,
            eligibility.spring_boot_detected,
            eligibility.spring_boot_conversion_eligible,
            eligibility.spring_boot_upgrade_eligible,
        )

        created_at = datetime.now(timezone.utc).isoformat()

        # 4. Save discovery-report.json.
        report = self._build_report(
            job_id, repo_url, owner, repo_name, analysis, eligibility, created_at
        )
        self._job_repository.save_discovery_report(job_id, report)

        # 5. Build the clean summary response.
        response = self._build_response(
            job_id, repo_url, owner, repo_name, visibility, analysis, eligibility
        )
        return DiscoveryOutcome(response=response, report=report)

    # -- builders ------------------------------------------------------------ #

    @staticmethod
    def _build_report(
        job_id: str,
        repo_url: str,
        owner: str,
        repo_name: str,
        analysis: ProjectAnalysis,
        eligibility: SpringBootEligibility,
        created_at: str,
    ) -> dict[str, Any]:
        return {
            "jobId": job_id,
            "status": STATUS_COMPLETED,
            "repoUrl": repo_url,
            "owner": owner,
            "repoName": repo_name,
            "buildTool": analysis.build_tool,
            "currentJavaVersion": analysis.current_java_version,
            "springBootVersion": analysis.spring_boot_version,
            "projectType": analysis.project_type,
            "multiModule": analysis.multi_module,
            "modules": analysis.modules,
            "dependencies": [dep.to_dict() for dep in analysis.dependencies],
            "buildPlugins": [plugin.to_dict() for plugin in analysis.build_plugins],
            "bomVersions": [bom.to_dict() for bom in analysis.bom_versions],
            "frameworks": analysis.frameworks,
            "dependencyCount": analysis.dependency_count,
            "javaMigrationEligible": eligibility.java_migration_eligible,
            "javaMigrationReason": eligibility.java_migration_reason,
            "springDetected": eligibility.spring_detected,
            "springBootDetected": eligibility.spring_boot_detected,
            "springBootConversionEligible": eligibility.spring_boot_conversion_eligible,
            "springBootUpgradeEligible": eligibility.spring_boot_upgrade_eligible,
            "eligibilityReason": eligibility.eligibility_reason,
            "frontend": analysis.frontend.to_dict(),
            "detectedFiles": {
                "pomXml": analysis.has_pom_xml,
                "buildGradle": analysis.has_build_gradle or analysis.has_build_gradle_kts,
                "packageJson": analysis.has_package_json,
            },
            "springBootConversion": eligibility.to_dict(),
            "createdAt": created_at,
        }

    @staticmethod
    def _build_response(
        job_id: str,
        repo_url: str,
        owner: str,
        repo_name: str,
        visibility: str,
        analysis: ProjectAnalysis,
        eligibility: SpringBootEligibility,
    ) -> dict[str, Any]:
        return {
            "jobId": job_id,
            "status": STATUS_COMPLETED,
            "message": "Repository discovery completed successfully.",
            "repository": {
                "repoUrl": repo_url,
                "owner": owner,
                "repoName": repo_name,
                "visibility": visibility,
            },
            "project": {
                "buildTool": analysis.build_tool,
                "currentJavaVersion": analysis.current_java_version,
                "springBootVersion": analysis.spring_boot_version,
                "projectType": analysis.project_type,
                "multiModule": analysis.multi_module,
                "modules": analysis.modules,
                "dependenciesCount": analysis.dependency_count,
                "frontendDetected": analysis.frontend.detected,
                "frontendType": analysis.frontend.type if analysis.frontend.detected else None,
                # --- extra fields consumed by the existing frontend UI ---
                "dependencies": [dep.to_dict() for dep in analysis.dependencies],
                "buildPlugins": [plugin.to_dict() for plugin in analysis.build_plugins],
                "bomVersions": [bom.to_dict() for bom in analysis.bom_versions],
                "frameworks": analysis.frameworks,
                "hasTests": analysis.has_tests,
                "javaFileCount": len(analysis.java_files),
                "defaultBranch": "main",
                "buildWarning": analysis.build_warning,
                "frontend": analysis.frontend.to_dict(),
                "detectedFiles": {
                    "pomXml": analysis.has_pom_xml,
                    "buildGradle": analysis.has_build_gradle,
                    "buildGradleKts": analysis.has_build_gradle_kts,
                    "packageJson": analysis.has_package_json,
                },
                "sourceLayout": {
                    "hasSrcMain": analysis.has_src_main,
                    "hasSrcTest": analysis.has_src_test,
                },
                "springFrameworkVersion": analysis.spring_framework_version,
                "springEntryClass": analysis.spring_entry_class,
                "javaMigrationEligible": eligibility.java_migration_eligible,
                "javaMigrationReason": eligibility.java_migration_reason,
                "springDetected": eligibility.spring_detected,
                "springBootDetected": eligibility.spring_boot_detected,
                "springBootConversionEligible": eligibility.spring_boot_conversion_eligible,
                "springBootUpgradeEligible": eligibility.spring_boot_upgrade_eligible,
                "eligibilityReason": eligibility.eligibility_reason,
                "springBootConversion": eligibility.to_dict(),
            },
            "nextStep": NEXT_STEP,
        }
