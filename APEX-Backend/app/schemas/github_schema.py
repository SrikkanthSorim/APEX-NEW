"""Response schema for the unversioned GitHub repo-visibility endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class RepoVisibilityResponse(BaseModel):
    """Body for ``GET /api/github/repo-visibility``."""

    owner: str
    repo: str
    visibility: str
    requires_token: bool
    message: str
