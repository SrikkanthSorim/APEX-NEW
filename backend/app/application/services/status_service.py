"""Reads/writes the migration job's state (`migration-report.json`).

Single source of truth for a running migration's status. Persisted to disk so
it survives a backend reload and can be polled by the Result page.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.infrastructure.workspace.workspace_paths import WorkspacePaths
from app.shared import json_utils


class MigrationReportStore:
    def __init__(self, paths: WorkspacePaths) -> None:
        self._paths = paths

    def read(self) -> dict[str, Any] | None:
        return json_utils.read_json(self._paths.migration_report_path)

    def write(self, report: dict[str, Any]) -> None:
        json_utils.write_json(self._paths.migration_report_path, report)

    def update(self, **fields: Any) -> dict[str, Any]:
        report = self.read() or {}
        report.update(fields)
        report["updatedAt"] = datetime.now(timezone.utc).isoformat()
        self.write(report)
        return report

    def append_logs(self, lines: list[str]) -> None:
        if not lines:
            return
        report = self.read() or {}
        existing = report.get("logLines") or []
        report["logLines"] = existing + lines
        self.write(report)

        # Mirror to the human-readable migration.log.
        self._paths.logs_dir.mkdir(parents=True, exist_ok=True)
        with self._paths.migration_log_path.open("a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line + "\n")
