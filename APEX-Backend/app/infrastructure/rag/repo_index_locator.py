"""Map a repository URL to its most recent discovery report on disk.

The chat widget identifies a repository by its URL (there is no job id at query
time), but discovery reports are stored per job under
``storage/migration-jobs/<jobId>/reports/discovery-report.json``. This locator
scans those reports and returns the newest one whose ``repoUrl`` matches, so the
chatbot can index (or re-index) a repository on demand from just its URL.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings


def _normalize_url(url: str) -> str:
    """Loosely normalize a GitHub URL for matching (case + trailing bits)."""
    text = (url or "").strip().lower()
    if text.endswith(".git"):
        text = text[:-4]
    return text.rstrip("/")


def find_report_by_job_id(job_id: str) -> dict[str, Any] | None:
    """Read a specific job's discovery report, if present."""
    path = settings.storage_dir / job_id / "reports" / "discovery-report.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def find_latest_report_by_url(repo_url: str) -> dict[str, Any] | None:
    """Return the newest discovery report matching ``repo_url`` (or None)."""
    target = _normalize_url(repo_url)
    if not target:
        return None

    storage_root: Path = settings.storage_dir
    if not storage_root.is_dir():
        return None

    best: dict[str, Any] | None = None
    best_created = ""
    for report_path in storage_root.glob("*/reports/discovery-report.json"):
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if _normalize_url(report.get("repoUrl", "")) != target:
            continue
        created = str(report.get("createdAt") or "")
        # ISO-8601 timestamps sort lexicographically; empty sorts oldest.
        if best is None or created > best_created:
            best, best_created = report, created
    return best
