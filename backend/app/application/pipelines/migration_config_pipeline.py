"""Migration Config pipeline.

Orchestrates the Migration Config stage (currently a single step: validate +
persist the configuration). Keeps a seam for future steps (e.g. pre-flight
checks against the target owner) without touching the controller.
"""

from __future__ import annotations

from typing import Any

from app.application.use_cases.save_migration_config import (
    MigrationConfigOutcome,
    SaveMigrationConfigUseCase,
)


class MigrationConfigPipeline:
    def __init__(self, save_use_case: SaveMigrationConfigUseCase | None = None) -> None:
        self._save_use_case = save_use_case or SaveMigrationConfigUseCase()

    def run(self, job_id: str, config: dict[str, Any]) -> MigrationConfigOutcome:
        return self._save_use_case.execute(job_id, config)
