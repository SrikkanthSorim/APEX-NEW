"""Connect Repository use case.

Responsibilities:
  * Validate & parse the GitHub repository URL.
  * Delegate public/private/access detection to the access checker.
  * Create a unique job id.
  * Persist a ``connect-report.json`` for the job.

It performs NO cloning, migration, or discovery work — that belongs to later
stages of the pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from app.core.exceptions import InvalidRepositoryUrlError
from app.infrastructure.github.repo_access_checker import RepoAccessChecker
from app.infrastructure.persistence.job_repository import JobRepository

# Accepts:
#   https://github.com/owner/repo        (with or without .git / trailing slash)
#   http://github.com/owner/repo
#   github.com/owner/repo
#   www.github.com/owner/repo
_GITHUB_URL_PATTERN = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/"
    r"(?P<owner>[^/\s]+)/(?P<repo>[^/\s?#]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedRepo:
    owner: str
    repo: str


@dataclass(frozen=True)
class ConnectResult:
    """What the use case returns to the pipeline/controller."""

    job_id: str
    repo_url: str
    owner: str
    repo_name: str
    repo_visibility: str
    access_status: str
    message: str
    created_at: str


def parse_github_url(repo_url: str) -> ParsedRepo:
    """Extract ``owner`` and ``repo`` from a GitHub URL.

    Raises :class:`InvalidRepositoryUrlError` when the URL is not a recognizable
    GitHub repository reference.
    """
    if not repo_url or not repo_url.strip():
        raise InvalidRepositoryUrlError()

    match = _GITHUB_URL_PATTERN.match(repo_url.strip())
    if not match:
        raise InvalidRepositoryUrlError()

    owner = match.group("owner").strip()
    repo = match.group("repo").strip()
    # Strip a trailing ``.git`` suffix if present.
    if repo.lower().endswith(".git"):
        repo = repo[:-4]

    if not owner or not repo:
        raise InvalidRepositoryUrlError()

    return ParsedRepo(owner=owner, repo=repo)


class ConnectRepositoryUseCase:
    def __init__(
        self,
        access_checker: RepoAccessChecker | None = None,
        job_repository: JobRepository | None = None,
    ) -> None:
        self._access_checker = access_checker or RepoAccessChecker()
        self._job_repository = job_repository or JobRepository()

    @staticmethod
    def _new_job_id() -> str:
        return f"job_{uuid4().hex[:12]}"

    @staticmethod
    def _success_message(is_private: bool) -> str:
        if is_private:
            return "Private repository access verified successfully."
        return "Repository access verified successfully."

    async def execute(self, repo_url: str, github_token: str | None) -> ConnectResult:
        # 1. Validate + parse the URL (raises InvalidRepositoryUrlError).
        parsed = parse_github_url(repo_url)

        # 2. Detect visibility / access (raises NotFound / AccessDenied / ServiceError).
        access = await self._access_checker.check(
            parsed.owner, parsed.repo, token=github_token
        )

        # 3. Create a unique job id.
        job_id = self._new_job_id()
        created_at = datetime.now(timezone.utc).isoformat()

        # 4. Persist the connect report locally.
        #
        # The GitHub PAT is deliberately NOT stored on disk. Persisting a secret
        # in plaintext JSON is a security risk; instead the later Discovery stage
        # re-receives the token from the client (or the GITHUB_TOKEN env fallback)
        # when it needs to clone a private repository.
        report = {
            "jobId": job_id,
            "repoUrl": repo_url,
            "owner": access.owner,
            "repoName": access.repo_name,
            "repoVisibility": access.visibility,
            "accessStatus": access.access_status,
            "createdAt": created_at,
        }
        self._job_repository.save_connect_report(job_id, report)

        return ConnectResult(
            job_id=job_id,
            repo_url=repo_url,
            owner=access.owner,
            repo_name=access.repo_name,
            repo_visibility=access.visibility,
            access_status=access.access_status,
            message=self._success_message(access.is_private),
            created_at=created_at,
        )
