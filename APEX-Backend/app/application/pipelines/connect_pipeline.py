"""Connect pipeline.

Orchestrates the Connect stage. For this stage the orchestration is a single
step (the connect use case), but keeping the pipeline seam means later stages
can add pre/post steps (validation, notifications, etc.) without touching the
controller.
"""

from __future__ import annotations

from app.application.use_cases.connect_repository import (
    ConnectRepositoryUseCase,
    ConnectResult,
)


class ConnectPipeline:
    def __init__(self, connect_use_case: ConnectRepositoryUseCase | None = None) -> None:
        self._connect_use_case = connect_use_case or ConnectRepositoryUseCase()

    async def run(self, repo_url: str, github_token: str | None) -> ConnectResult:
        return await self._connect_use_case.execute(repo_url, github_token)
