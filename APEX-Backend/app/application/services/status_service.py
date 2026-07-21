"""Reads/writes the migration job's state (`migration-report.json`).

Single source of truth for a running migration's status. Persisted to disk so
it survives a backend reload and can be polled by the Result page.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.infrastructure.workspace.workspace_paths import WorkspacePaths
from app.shared import json_utils
from app.shared import migration_log_sanitizer


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
        """Persist ``lines`` for this job's log stream.

        The *raw*, unmodified lines are mirrored to the human-readable
        ``migration.log`` file on disk for developer/backend troubleshooting
        (never served by any API). Only the sanitized, user-facing versions
        (see ``migration_log_sanitizer``) are stored in ``logLines`` -- the
        field every polling/API/report consumer reads from -- so raw
        OpenRewrite/Maven/Gradle internals never reach the Migration Log UI.
        """
        if not lines:
            return

        # Mirror the raw lines to the human-readable migration.log first,
        # unsanitized -- this is the only place full detail is kept.
        self._paths.logs_dir.mkdir(parents=True, exist_ok=True)
        with self._paths.migration_log_path.open("a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line + "\n")

        sanitized = migration_log_sanitizer.sanitize_lines(lines)
        if not sanitized:
            return
        report = self.read() or {}
        existing = report.get("logLines") or []
        report["logLines"] = existing + [line for line in sanitized if line not in existing]
        self.write(report)
