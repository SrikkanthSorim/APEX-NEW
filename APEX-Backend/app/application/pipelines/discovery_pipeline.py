"""Discovery pipeline.

Orchestrates the Discovery stage: it reads the job details, prepares the
workspace, and runs the discovery use case. Keeping this seam lets later
enhancements (progress events, caching, notifications) slot in without touching
the controller.

The work is synchronous (git clone + filesystem analysis); the controller runs
it in a threadpool so the event loop is never blocked.
"""

from __future__ import annotations

from app.application.use_cases.run_discovery import DiscoveryOutcome, RunDiscoveryUseCase


class DiscoveryPipeline:
    def __init__(self, run_discovery: RunDiscoveryUseCase | None = None) -> None:
        self._run_discovery = run_discovery or RunDiscoveryUseCase()

    def run(self, job_id: str, github_token: str | None = None) -> DiscoveryOutcome:
        return self._run_discovery.execute(job_id, github_token)
