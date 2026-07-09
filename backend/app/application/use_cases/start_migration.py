"""Start Migration use case.

Runs OpenRewrite (Java upgrade + javax->jakarta) on a copy of the cloned repo,
then publishes the result to the configured destination (a new repo under
Javaapex by default). Long-running; driven in a background thread by the
pipeline. All state is persisted to ``migration-report.json`` for polling.
original-repo is never modified.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.application.services import progress_service
from app.application.services.status_service import MigrationReportStore
from app.core.config import settings
from app.core.exceptions import (
    DiscoveryReportRequiredError,
    MigrationExecutionError,
    MigrationJobNotFoundError,
)
from app.domain.enums.migration_status import MigrationStatus, MigrationStep
from app.infrastructure.build.build_validator import BuildValidator
from app.infrastructure.github.branch_creator import BranchCreator
from app.infrastructure.github.repo_creator import RepoCreator
from app.infrastructure.github.repo_pusher import RepoPusher
from app.infrastructure.migration_engine.automated_migration_runner import (
    AutomatedMigrationRunner,
)
from app.infrastructure.persistence.job_repository import JobRepository
from app.infrastructure.workspace.workspace_manager import WorkspaceManager
from app.infrastructure.workspace.workspace_paths import WorkspacePaths
from app.shared import file_utils

logger = logging.getLogger(__name__)

MODE_CREATE_NEW_REPO = "CREATE_NEW_REPO"
MODE_EXISTING_REPO_BRANCH = "EXISTING_REPO_BRANCH"
MODE_LOCAL_FOLDER = "LOCAL_FOLDER"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StartMigrationUseCase:
    def __init__(
        self,
        job_repository: JobRepository | None = None,
        runner: AutomatedMigrationRunner | None = None,
        repo_creator: RepoCreator | None = None,
        repo_pusher: RepoPusher | None = None,
        branch_creator: BranchCreator | None = None,
        build_validator: BuildValidator | None = None,
    ) -> None:
        self._job_repository = job_repository or JobRepository()
        self._runner = runner or AutomatedMigrationRunner()
        self._repo_creator = repo_creator or RepoCreator()
        self._repo_pusher = repo_pusher or RepoPusher()
        self._branch_creator = branch_creator or BranchCreator()
        self._build_validator = build_validator or BuildValidator()

    # ------------------------------------------------------------------ #
    # Phase 1: validate + write the initial queued report (synchronous)
    # ------------------------------------------------------------------ #
    def prepare(self, job_id: str, request: dict[str, Any] | None) -> dict[str, Any]:
        if not self._job_repository.job_exists(job_id):
            raise MigrationJobNotFoundError()

        connect = self._job_repository.read_connect_report(job_id)
        discovery = self._job_repository.read_discovery_report(job_id)
        if not connect or not discovery:
            raise DiscoveryReportRequiredError()

        config = self._job_repository.read_migration_config_report(job_id) or {}
        request = request or {}

        source_repo_url = connect.get("repoUrl") or discovery.get("repoUrl") or ""
        build_tool = (discovery.get("buildTool") or "").upper()
        source_java = (
            config.get("sourceJavaVersion")
            or request.get("source_java_version")
            or discovery.get("currentJavaVersion")
            or ""
        )
        target_java = (
            config.get("targetJavaVersion") or request.get("target_java_version") or ""
        )
        if not target_java:
            raise MigrationExecutionError("No target Java version selected.")

        destination = self._resolve_destination(config, connect)

        store = MigrationReportStore(WorkspacePaths(job_id))
        report = {
            "jobId": job_id,
            "status": MigrationStatus.QUEUED.value,
            "currentStep": MigrationStep.QUEUED.value,
            "progressPercent": 0,
            "sourceRepoUrl": source_repo_url,
            "sourceJavaVersion": str(source_java),
            "targetJavaVersion": str(target_java),
            "buildTool": build_tool,
            "conversionTypes": config.get("conversionTypes")
            or request.get("conversion_types")
            or [],
            "destination": destination,
            "targetRepo": None,
            "startedAt": _now(),
            "completedAt": None,
            "errorMessage": None,
            "filesModified": 0,
            "recipes": [],
            "usedFallback": False,
            "logLines": [],
        }
        store.write(report)
        logger.info("Migration queued for job %s (target Java %s)", job_id, target_java)
        return report

    # ------------------------------------------------------------------ #
    # Phase 2: the long-running job (runs in a background thread)
    # ------------------------------------------------------------------ #
    def run(self, job_id: str) -> None:
        paths = WorkspacePaths(job_id)
        store = MigrationReportStore(paths)
        report = store.read() or {}
        build_tool = report.get("buildTool", "")
        target_java = report.get("targetJavaVersion", "")

        try:
            # --- Prepare migrated-repo ---
            progress_service.set_phase(
                store, status=MigrationStatus.RUNNING.value,
                step=MigrationStep.PREPARING.value, percent=10,
            )
            WorkspaceManager(paths).prepare_migrated_repo()

            # --- Run OpenRewrite (Java upgrade + jakarta) ---
            progress_service.set_phase(
                store, status=MigrationStatus.RUNNING.value,
                step=MigrationStep.MIGRATING.value, percent=35,
            )
            result = self._runner.run(
                paths.migrated_repo_dir, build_tool, target_java, include_jakarta=True
            )
            store.append_logs(result.log_lines + result.error_lines)
            self._log_migration_error_lines(job_id, result.error_lines)
            store.update(recipes=result.recipes, usedFallback=result.used_fallback)

            if not result.success:
                self._fail(store, job_id, "OpenRewrite migration failed. See logs for details.")
                return

            files_modified = file_utils.count_changed_files(
                paths.original_repo_dir, paths.migrated_repo_dir
            )
            store.update(filesModified=files_modified, progressPercent=60)
            logger.info("Migration changed %d file(s) for job %s", files_modified, job_id)

            # --- Validate the migrated code still builds ---
            progress_service.set_phase(
                store, status=MigrationStatus.RUNNING.value,
                step=MigrationStep.VALIDATING.value, percent=70,
            )
            self._validate_build(store, job_id, result.project_dir, build_tool)

            # --- Publish ---
            progress_service.set_phase(
                store, status=MigrationStatus.RUNNING.value,
                step=MigrationStep.PUBLISHING.value, percent=85,
            )
            target_repo = self._publish(store, report, paths, target_java)

            # --- Done ---
            store.update(
                status=MigrationStatus.COMPLETED.value,
                currentStep=MigrationStep.COMPLETED.value,
                progressPercent=100,
                targetRepo=target_repo,
                completedAt=_now(),
            )
            store.append_logs([f"Migration completed. Published to {target_repo}"])
            logger.info("Migration completed for job %s -> %s", job_id, target_repo)

        except MigrationExecutionError as exc:
            self._fail(store, job_id, exc.message)
        except Exception as exc:  # noqa: BLE001 - report any unexpected failure cleanly
            logger.exception("Unexpected migration failure for job %s", job_id)
            self._fail(store, job_id, "Migration failed due to an unexpected error.")

    @staticmethod
    def _log_migration_error_lines(job_id: str, error_lines: list[str]) -> None:
        for line in error_lines[:10]:
            logger.warning("Migration tool error for job %s: %s", job_id, line)

    # -- build validation ---------------------------------------------------- #

    def _validate_build(
        self,
        store: MigrationReportStore,
        job_id: str,
        project_dir: Any,
        build_tool: str,
    ) -> None:
        """Compile/package the migrated code and record BUILD SUCCESS/FAILED.

        Non-blocking: a failed build is reported (logs + report) but the migrated
        repo is still published so it can be inspected.
        """
        if project_dir is None:
            return

        logger.info("Validating build for job %s (%s) ...", job_id, build_tool)
        result = self._build_validator.validate(project_dir, build_tool)

        store.update(buildStatus=result.status_label, buildSuccess=result.success)
        # Surface the outcome + the tail of the build log to the UI/log.
        store.append_logs(
            [f"===== {result.status_label} ({result.tool}) ====="]
            + result.error_lines[:20]
            + result.log_lines[-15:]
        )

        if result.skipped:
            logger.info("Build validation skipped for job %s", job_id)
        elif result.success:
            logger.info("BUILD SUCCESS for job %s (migrated repo compiles)", job_id)
        else:
            # Surface the actual reason (e.g. AccessDeniedException from AV locking
            # the Gradle cache) instead of a generic "did not build".
            detail_lines = result.error_lines[:10] or result.log_lines[-10:]
            detail = " | ".join(detail_lines) if detail_lines else "no build output captured"
            logger.warning(
                "BUILD FAILED for job %s (migrated repo did not build): %s", job_id, detail
            )

    # -- publish per destination mode --------------------------------------- #

    def _publish(
        self,
        store: MigrationReportStore,
        report: dict[str, Any],
        paths: WorkspacePaths,
        target_java: str,
    ) -> str:
        destination = report.get("destination") or {}
        mode = destination.get("mode", MODE_CREATE_NEW_REPO)
        commit_message = f"Migrate to Java {target_java} via OpenRewrite (javax->jakarta)"

        if mode == MODE_LOCAL_FOLDER:
            store.append_logs(["Local destination: migrated code left in the workspace."])
            return str(paths.migrated_repo_dir)

        if mode == MODE_EXISTING_REPO_BRANCH:
            branch = destination.get("targetBranch") or "migration"
            source_url = report.get("sourceRepoUrl") or ""
            self._branch_creator.push_branch(
                paths.migrated_repo_dir, source_url, branch, commit_message=commit_message
            )
            return f"{source_url.rstrip('/').removesuffix('.git')}/tree/{branch}"

        # Default: create a new repo under the configured owner and push.
        created = self._repo_creator.create(
            destination.get("targetRepoName") or "",
            owner=destination.get("targetOwner"),
            host=destination.get("targetHost"),
        )
        self._repo_pusher.push(
            paths.migrated_repo_dir, created.clone_url, commit_message=commit_message
        )
        return created.html_url

    # -- helpers ------------------------------------------------------------- #

    @staticmethod
    def _resolve_destination(config: dict[str, Any], connect: dict[str, Any]) -> dict[str, Any]:
        destination = dict(config.get("destination") or {})
        if destination.get("mode"):
            return destination
        # No saved config — default to a new repo under the configured owner.
        repo_name = connect.get("repoName") or "repo"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return {
            "mode": MODE_CREATE_NEW_REPO,
            "targetOwner": settings.github_target_owner,
            "targetHost": "github.com",
            "targetRepoName": f"{repo_name}-Migrated{timestamp}",
        }

    @staticmethod
    def _fail(store: MigrationReportStore, job_id: str, message: str) -> None:
        store.append_logs([f"ERROR: {message}"])
        store.update(
            status=MigrationStatus.FAILED.value,
            currentStep=MigrationStep.FAILED.value,
            errorMessage=message,
            completedAt=_now(),
        )
        logger.warning("Migration failed for job %s: %s", job_id, message)
