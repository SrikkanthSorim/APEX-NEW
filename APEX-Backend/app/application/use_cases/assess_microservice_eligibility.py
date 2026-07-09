"""Microservice Eligibility Assessment use case.

Runs the analyzer over a job's already-cloned ``original-repo`` workspace (the
same clone Discovery made) — no re-cloning and no GitHub API calls, so it
works for any repo Discovery has run on.
"""

from __future__ import annotations

from app.core.exceptions import RepositoryWorkspaceNotFoundError
from app.infrastructure.analyzers.microservice.eligibility_assessor import MicroserviceEligibilityAssessor
from app.infrastructure.persistence.job_repository import JobRepository
from app.infrastructure.workspace.workspace_paths import WorkspacePaths


class AssessMicroserviceEligibilityUseCase:
    def __init__(
        self,
        assessor: MicroserviceEligibilityAssessor | None = None,
        job_repository: JobRepository | None = None,
    ) -> None:
        self._assessor = assessor or MicroserviceEligibilityAssessor()
        self._job_repository = job_repository or JobRepository()

    def execute(self, job_id: str) -> dict:
        paths = WorkspacePaths(job_id)
        if not paths.original_repo_dir.is_dir():
            raise RepositoryWorkspaceNotFoundError()

        connect_report = self._job_repository.read_connect_report(job_id) or {}
        project_name = connect_report.get("repoName") or job_id

        return self._assessor.assess(paths.original_repo_dir, project_name=project_name)
