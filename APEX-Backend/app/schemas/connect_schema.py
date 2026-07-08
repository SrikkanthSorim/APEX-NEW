"""Request/response schemas for the Connect endpoint.

These are the HTTP boundary contracts. The camelCase field names match what the
frontend sends and expects.
"""

from typing import Optional

from pydantic import BaseModel, Field


class ConnectRequest(BaseModel):
    """Body for ``POST /api/v1/connect``."""

    repo_url: str = Field(
        ...,
        alias="repoUrl",
        description="GitHub repository URL, e.g. https://github.com/owner/repo",
    )
    github_token: Optional[str] = Field(
        default=None,
        alias="githubToken",
        description="Optional GitHub token, required only for private repositories.",
    )

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "repoUrl": "https://github.com/owner/repo",
                "githubToken": "ghp_xxxxxxxxxxxxxxxxxxxx",
            }
        },
    }


class ConnectResponse(BaseModel):
    """Success body for ``POST /api/v1/connect``."""

    job_id: str = Field(..., alias="jobId")
    repo_url: str = Field(..., alias="repoUrl")
    owner: str
    repo_name: str = Field(..., alias="repoName")
    repo_visibility: str = Field(..., alias="repoVisibility")
    access_status: str = Field(..., alias="accessStatus")
    message: str

    model_config = {"populate_by_name": True}


class ConnectErrorResponse(BaseModel):
    """Error body for a failed connect attempt."""

    access_status: str = Field(..., alias="accessStatus")
    message: str

    model_config = {"populate_by_name": True}
