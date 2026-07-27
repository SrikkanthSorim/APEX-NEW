"""Migration job statuses and step labels.

Status values match what the frontend polling treats as terminal
(``completed``, ``failed``, ``cancelled``).
"""

from __future__ import annotations

from enum import Enum


class MigrationStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {
    MigrationStatus.COMPLETED.value,
    MigrationStatus.FAILED.value,
    MigrationStatus.CANCELLED.value,
}


class MigrationStep(str, Enum):
    """Human-readable current-step labels shown in the UI/progress bar."""

    QUEUED = "Queued"
    PREPARING = "Preparing workspace"
    MIGRATING = "Executing Migration"
    VALIDATING = "Validating build"
    TESTING = "Running unit tests"
    QUALITY_GATES = "Running quality gates"
    PUBLISHING = "Publishing to GitHub"
    COMPLETED = "Migration completed"
    FAILED = "Migration failed"
