"""Migration Execution pipeline.

Orchestrates Start Migration: validates + queues the job, runs the long
migration in a background thread, and exposes read accessors for polling
(summary / detail / logs) built from the persisted report.
"""

from __future__ import annotations

import threading
from typing import Any

from app.application.services import report_service
from app.application.services.status_service import MigrationReportStore
from app.application.use_cases.start_migration import StartMigrationUseCase
from app.core.exceptions import MigrationJobNotFoundError
from app.infrastructure.persistence.job_repository import JobRepository
from app.infrastructure.workspace.workspace_paths import WorkspacePaths


class MigrationExecutionPipeline:
    def __init__(
        self, use_case: StartMigrationUseCase | None = None, job_repository: JobRepository | None = None
    ) -> None:
        self._use_case = use_case or StartMigrationUseCase()
        self._job_repository = job_repository or JobRepository()

    def start(self, job_id: str, request: dict[str, Any] | None) -> dict[str, Any]:
        """Validate + queue, launch the background run, return the initial result."""
        report = self._use_case.prepare(job_id, request)

        thread = threading.Thread(
            target=self._use_case.run,
            args=(job_id,),
            name=f"migration-{job_id}",
            daemon=True,
        )
        thread.start()

        return report_service.build_result(report, self._job_repository.read_unit_test_report(job_id))

    def get_summary(self, job_id: str) -> dict[str, Any]:
        return report_service.build_summary(
            self._require_report(job_id), self._job_repository.read_unit_test_report(job_id)
        )

    def get_detail(self, job_id: str) -> dict[str, Any]:
        return report_service.build_result(
            self._require_report(job_id), self._job_repository.read_unit_test_report(job_id)
        )

    def get_logs(self, job_id: str) -> dict[str, Any]:
        return report_service.build_logs(self._require_report(job_id))

    def get_fossa(self, job_id: str) -> dict[str, Any]:
        return report_service.build_fossa(self._require_report(job_id))

    # -- helpers ------------------------------------------------------------- #

    @staticmethod
    def _require_report(job_id: str) -> dict[str, Any]:
        report = MigrationReportStore(WorkspacePaths(job_id)).read()
        if not report:
            raise MigrationJobNotFoundError()
        return report
