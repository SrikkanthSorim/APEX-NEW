"""Response schemas for the unversioned GitHub utility endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class RepoVisibilityResponse(BaseModel):
    """Body for ``GET /api/github/repo-visibility``."""

    owner: str
    repo: str
    visibility: str
    requires_token: bool
    message: str


class RepoFileItem(BaseModel):
    """One entry in a repository directory listing (matches the frontend ``RepoFile``)."""

    name: str
    path: str
    type: str  # "file" | "dir"
    size: int
    url: str


class RepoFilesResponse(BaseModel):
    """Body for ``GET /api/github/list-files``."""

    repo_url: str
    owner: str
    repo: str
    path: str
    files: list[RepoFileItem]


class FileContentResponse(BaseModel):
    """Body for ``GET /api/github/file-content``."""

    repo_url: str
    owner: str
    repo: str
    file_path: str
    content: str


class RepoUrlAnalysisResponse(BaseModel):
    """Body for ``GET /api/github/analyze-url``."""

    repo_url: str
    owner: str
    repo: str
    analysis: dict[str, Any]
