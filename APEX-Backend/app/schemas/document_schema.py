"""Schemas for generated repository-grounded technical documents."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class TechnicalDocumentRequest(BaseModel):
    repo_url: Optional[str] = Field(default=None, alias="repo_url")
    repository_url: Optional[str] = Field(default=None, alias="repository_url")
    source_repo_url: Optional[str] = Field(default=None, alias="source_repo_url")
    token: Optional[str] = None
    github_token: Optional[str] = Field(default=None, alias="github_token")
    job_id: Optional[str] = Field(default=None, alias="job_id")
    migration_job_id: Optional[str] = Field(default=None, alias="migration_job_id")
    source_repo: Optional[str] = Field(default=None, alias="source_repo")
    target_repo: Optional[str] = Field(default=None, alias="target_repo")
    source_java_version: Optional[str] = Field(default=None, alias="source_java_version")
    target_java_version: Optional[str] = Field(default=None, alias="target_java_version")
    document_type: Optional[str] = Field(default="TECHNICAL_SPECIFICATION", alias="document_type")
    analysis: Optional[dict[str, Any]] = None

    model_config = {"populate_by_name": True, "extra": "ignore"}


class TechnicalDocumentResponse(BaseModel):
    filename: str
    html: str
    document_type: str = Field(default="TECHNICAL_SPECIFICATION", alias="document_type")

    model_config = {"populate_by_name": True}
