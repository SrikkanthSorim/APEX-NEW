"""Small helper to advance a migration's phase (status + step + progress)."""

from __future__ import annotations

from typing import Any

from app.application.services.status_service import MigrationReportStore


def set_phase(
    store: MigrationReportStore,
    *,
    status: str,
    step: str,
    percent: int,
    **extra: Any,
) -> dict[str, Any]:
    """Update status/current-step/progress (plus any extra fields) in one write."""
    return store.update(
        status=status,
        currentStep=step,
        progressPercent=percent,
        **extra,
    )
