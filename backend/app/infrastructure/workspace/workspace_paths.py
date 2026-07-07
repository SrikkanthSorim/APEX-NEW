"""Canonical filesystem layout for a migration job.

Single source of truth for where each job artifact lives::

    storage/migration-jobs/<jobId>/
        original-repo/                 # read-only clone (Discovery)
        reports/
            connect-report.json
            discovery-report.json
        logs/
            discovery.log

``migrated-repo/`` is intentionally NOT created here — it belongs to the
Start Migration stage.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings


class WorkspacePaths:
    """Resolves the standard paths for a single job."""

    def __init__(self, job_id: str, storage_dir: Path | None = None) -> None:
        self.job_id = job_id
        self._storage_dir = Path(storage_dir) if storage_dir else settings.storage_dir

    @property
    def job_dir(self) -> Path:
        return self._storage_dir / self.job_id

    @property
    def original_repo_dir(self) -> Path:
        return self.job_dir / "original-repo"

    @property
    def reports_dir(self) -> Path:
        return self.job_dir / "reports"

    @property
    def logs_dir(self) -> Path:
        return self.job_dir / "logs"

    @property
    def connect_report_path(self) -> Path:
        return self.reports_dir / "connect-report.json"

    @property
    def discovery_report_path(self) -> Path:
        return self.reports_dir / "discovery-report.json"

    @property
    def discovery_log_path(self) -> Path:
        return self.logs_dir / "discovery.log"
