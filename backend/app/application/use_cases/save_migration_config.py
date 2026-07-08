"""Save Migration Config use case.

Validates and persists the migration destination + selected options as
``migration-config-report.json``. It does NOT create repos, push, or run any
migration — that is the Start Migration stage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.exceptions import InvalidMigrationConfigError, MigrationJobNotFoundError
from app.infrastructure.persistence.job_repository import JobRepository

logger = logging.getLogger(__name__)

MODE_CREATE_NEW_REPO = "CREATE_NEW_REPO"
MODE_EXISTING_REPO_BRANCH = "EXISTING_REPO_BRANCH"
MODE_LOCAL_FOLDER = "LOCAL_FOLDER"
VALID_MODES = {MODE_CREATE_NEW_REPO, MODE_EXISTING_REPO_BRANCH, MODE_LOCAL_FOLDER}

# Default GitHub owner that migrated repositories are published under.
DEFAULT_TARGET_OWNER = "Javaapex"
DEFAULT_TARGET_HOST = "github.com"

STATUS_SAVED = "MIGRATION_CONFIG_SAVED"
NEXT_STEP = "START_MIGRATION"


@dataclass(frozen=True)
class MigrationConfigOutcome:
    response: dict[str, Any]
    report: dict[str, Any]


class SaveMigrationConfigUseCase:
    def __init__(self, job_repository: JobRepository | None = None) -> None:
        self._job_repository = job_repository or JobRepository()

    def execute(self, job_id: str, config: dict[str, Any]) -> MigrationConfigOutcome:
        # 1. Job must exist (created during Connect).
        if not self._job_repository.job_exists(job_id):
            raise MigrationJobNotFoundError()

        # 2. Validate the destination.
        destination = dict(config.get("destination") or {})
        destination = self._validate_destination(destination)

        # 3. Build + persist the report.
        created_at = datetime.now(timezone.utc).isoformat()
        report = {
            "jobId": job_id,
            "status": STATUS_SAVED,
            "sourceRepoUrl": config.get("sourceRepoUrl"),
            "sourceJavaVersion": config.get("sourceJavaVersion"),
            "targetJavaVersion": config.get("targetJavaVersion"),
            "buildTool": config.get("buildTool"),
            "conversionTypes": config.get("conversionTypes") or [],
            "options": config.get("options") or {},
            "destination": destination,
            "createdAt": created_at,
        }
        self._job_repository.save_migration_config_report(job_id, report)

        logger.info(
            "Migration config saved for job %s: mode=%s owner=%s target=%s",
            job_id,
            destination.get("mode"),
            destination.get("targetOwner"),
            destination.get("targetRepoName") or destination.get("targetBranch")
            or destination.get("localFolder"),
        )

        response = {
            "jobId": job_id,
            "status": STATUS_SAVED,
            "message": "Migration configuration saved successfully.",
            "destination": destination,
            "nextStep": NEXT_STEP,
        }
        return MigrationConfigOutcome(response=response, report=report)

    # -- validation ---------------------------------------------------------- #

    @staticmethod
    def _validate_destination(destination: dict[str, Any]) -> dict[str, Any]:
        mode = str(destination.get("mode") or "").strip().upper()
        if mode not in VALID_MODES:
            raise InvalidMigrationConfigError("Unknown migration destination mode.")
        destination["mode"] = mode

        if mode == MODE_CREATE_NEW_REPO:
            # Migrated repos are published under the configured owner (Javaapex).
            if not destination.get("targetOwner"):
                destination["targetOwner"] = DEFAULT_TARGET_OWNER
            if not destination.get("targetHost"):
                destination["targetHost"] = DEFAULT_TARGET_HOST
            if not (destination.get("targetRepoName") or destination.get("targetRepoUrl")):
                raise InvalidMigrationConfigError(
                    "A target repository name is required to create a new repository."
                )
        elif mode == MODE_EXISTING_REPO_BRANCH:
            if not destination.get("targetBranch"):
                raise InvalidMigrationConfigError(
                    "A target branch is required for the existing-repository option."
                )
        elif mode == MODE_LOCAL_FOLDER:
            if not destination.get("localFolder"):
                raise InvalidMigrationConfigError(
                    "A local folder name is required for the local option."
                )

        return destination
