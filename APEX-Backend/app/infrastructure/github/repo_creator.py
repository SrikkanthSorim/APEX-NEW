"""Creates the target repository under the configured owner (Javaapex)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import settings
from app.core.exceptions import PushFailedError
from app.infrastructure.github.github_client import GithubClient
from app.infrastructure.github.profile_resolver import ProfileResolver, TargetProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CreatedRepo:
    owner: str
    name: str
    html_url: str
    clone_url: str


class RepoCreator:
    def __init__(
        self,
        github_client: GithubClient | None = None,
        profile_resolver: ProfileResolver | None = None,
    ) -> None:
        self._github = github_client or GithubClient()
        self._profiles = profile_resolver or ProfileResolver(self._github)

    def create(
        self,
        repo_name: str,
        *,
        owner: str | None = None,
        host: str | None = None,
        private: bool = False,
        description: str = "Migrated with OpenRewrite by Java APEX",
    ) -> CreatedRepo:
        token = (settings.github_target_token or "").strip()
        if not token:
            raise PushFailedError(
                "No target GitHub token configured. Set GITHUB_TARGET_TOKEN."
            )

        profile: TargetProfile = self._profiles.resolve(owner=owner, host=host)
        logger.info(
            "Creating repo %s/%s (%s)",
            profile.owner,
            repo_name,
            "org" if profile.is_org else "user",
        )

        response = self._github.create_repository_sync(
            profile.owner,
            repo_name,
            token,
            is_org=profile.is_org,
            private=private,
            description=description,
        )

        if response.status_code in (200, 201) and isinstance(response.data, dict):
            data = response.data
            return CreatedRepo(
                owner=profile.owner,
                name=str(data.get("name", repo_name)),
                html_url=str(data.get("html_url", f"https://{profile.host}/{profile.owner}/{repo_name}")),
                clone_url=str(data.get("clone_url", f"https://{profile.host}/{profile.owner}/{repo_name}.git")),
            )

        raise PushFailedError(self._error_message(response.status_code, response.data))

    @staticmethod
    def _error_message(status_code: int, data: dict | None) -> str:
        detail = ""
        if isinstance(data, dict):
            detail = str(data.get("message", ""))
        if status_code == 401:
            return "Target GitHub token is invalid. Check GITHUB_TARGET_TOKEN."
        if status_code == 403:
            return "Target token lacks permission to create repositories in this owner."
        if status_code == 404:
            return "Target owner not found, or the token cannot access it."
        if status_code == 422 and "already exists" in detail.lower():
            return "A repository with this name already exists under the target owner."
        return f"Could not create the target repository ({status_code})."
