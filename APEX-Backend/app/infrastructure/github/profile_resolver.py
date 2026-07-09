"""Resolves the target GitHub owner (org vs user) for publishing."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.infrastructure.github.github_client import GithubClient


@dataclass(frozen=True)
class TargetProfile:
    owner: str
    is_org: bool
    host: str = "github.com"


class ProfileResolver:
    def __init__(self, github_client: GithubClient | None = None) -> None:
        self._github = github_client or GithubClient()

    def resolve(self, owner: str | None = None, host: str | None = None) -> TargetProfile:
        resolved_owner = (owner or settings.github_target_owner or "").strip()
        owner_type = self._github.get_owner_type_sync(
            resolved_owner, token=settings.github_target_token or None
        )
        # Default to treating it as an org when detection is inconclusive (the
        # configured owner is an org in the common case). Falls back to user.
        is_org = owner_type != "User"
        return TargetProfile(
            owner=resolved_owner,
            is_org=is_org,
            host=(host or "github.com"),
        )
