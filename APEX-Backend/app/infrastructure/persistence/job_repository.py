"""Local filesystem persistence for migration jobs.

For now, job data lives on disk under::

    storage/migration-jobs/<jobId>/reports/connect-report.json

This can later be swapped for a database-backed implementation without changing
the application layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings


class JobRepository:
    """Persists per-job artifacts on the local filesystem."""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self._storage_dir = Path(storage_dir) if storage_dir else settings.storage_dir

    def _job_dir(self, job_id: str) -> Path:
        return self._storage_dir / job_id

    def _reports_dir(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "reports"

    def save_connect_report(self, job_id: str, report: dict[str, Any]) -> Path:
        """Write ``connect-report.json`` for the given job and return its path."""
        reports_dir = self._reports_dir(job_id)
        reports_dir.mkdir(parents=True, exist_ok=True)

        report_path = reports_dir / "connect-report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report_path

    def read_connect_report(self, job_id: str) -> dict[str, Any] | None:
        """Read back a previously saved connect report, if it exists."""
        report_path = self._reports_dir(job_id) / "connect-report.json"
        if not report_path.exists():
            return None
        return json.loads(report_path.read_text(encoding="utf-8"))

    def save_discovery_report(self, job_id: str, report: dict[str, Any]) -> Path:
        """Write ``discovery-report.json`` for the given job and return its path."""
        reports_dir = self._reports_dir(job_id)
        reports_dir.mkdir(parents=True, exist_ok=True)

        report_path = reports_dir / "discovery-report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report_path

    def read_discovery_report(self, job_id: str) -> dict[str, Any] | None:
        """Read back a previously saved discovery report, if it exists."""
        report_path = self._reports_dir(job_id) / "discovery-report.json"
        if not report_path.exists():
            return None
        return json.loads(report_path.read_text(encoding="utf-8"))

    def save_migration_config_report(self, job_id: str, report: dict[str, Any]) -> Path:
        """Write ``migration-config-report.json`` for the job and return its path."""
        reports_dir = self._reports_dir(job_id)
        reports_dir.mkdir(parents=True, exist_ok=True)

        report_path = reports_dir / "migration-config-report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report_path

    def read_migration_config_report(self, job_id: str) -> dict[str, Any] | None:
        """Read back a previously saved migration config report, if it exists."""
        report_path = self._reports_dir(job_id) / "migration-config-report.json"
        if not report_path.exists():
            return None
        return json.loads(report_path.read_text(encoding="utf-8"))

    def save_unit_test_report(self, job_id: str, report: dict[str, Any]) -> Path:
        """Write ``unit-test-report.json`` for the given job and return its path."""
        reports_dir = self._reports_dir(job_id)
        reports_dir.mkdir(parents=True, exist_ok=True)

        report_path = reports_dir / "unit-test-report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report_path

    def read_unit_test_report(self, job_id: str) -> dict[str, Any] | None:
        """Read back a previously saved unit test report, if it exists."""
        report_path = self._reports_dir(job_id) / "unit-test-report.json"
        if not report_path.exists():
            return None
        return json.loads(report_path.read_text(encoding="utf-8"))

    def job_exists(self, job_id: str) -> bool:
        """True if the job directory (created during Connect) exists on disk."""
        return self._job_dir(job_id).is_dir()
