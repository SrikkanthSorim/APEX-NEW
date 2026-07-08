"""Thin async client over the GitHub REST API.

This module only knows how to *talk* to GitHub. It performs no business
decisions about visibility or access — that lives in ``repo_access_checker``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import GithubServiceError


@dataclass(frozen=True)
class GithubRepoResponse:
    """Normalized result of a ``GET /repos/{owner}/{repo}`` call."""

    status_code: int
    data: dict[str, Any] | None


class GithubClient:
    """Async wrapper around the handful of GitHub endpoints Connect needs."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._base_url = (base_url or settings.github_api_base_url).rstrip("/")
        self._timeout = timeout or settings.github_request_timeout_seconds

    def _headers(self, token: str | None) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "java-migration-platform",
        }
        # Prefer the caller token; otherwise fall back to a configured server
        # token (GITHUB_TOKEN). A configured token raises the API rate limit from
        # 60/hr (unauthenticated) to 5000/hr, which matters during heavy testing.
        effective_token = (token or "").strip() or (settings.github_token or "").strip()
        if effective_token:
            headers["Authorization"] = f"Bearer {effective_token}"
        return headers

    async def get_repository(
        self,
        owner: str,
        repo: str,
        token: str | None = None,
    ) -> GithubRepoResponse:
        """Fetch repository metadata.

        Returns the HTTP status and parsed JSON body (when present). Network or
        transport failures are surfaced as :class:`GithubServiceError`; HTTP
        status codes (404/401/403/...) are returned to the caller for
        interpretation.
        """
        url = f"{self._base_url}/repos/{owner}/{repo}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=self._headers(token))
        except httpx.HTTPError as exc:  # transport / timeout / DNS
            raise GithubServiceError() from exc

        data: dict[str, Any] | None = None
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                data = parsed
        except ValueError:
            data = None

        return GithubRepoResponse(status_code=response.status_code, data=data)
