"""Request/response schemas for the Discovery endpoint.

camelCase field names match what the frontend sends/expects. The endpoint works
with no body; ``githubToken`` is an optional override used for private repos when
it is not already stored in the connect report.
"""

from typing import Optional

from pydantic import BaseModel, Field


class DiscoveryRequest(BaseModel):
    """Optional body for ``POST /api/v1/discovery/{jobId}``."""

    github_token: Optional[str] = Field(
        default=None,
        alias="githubToken",
        description="Optional GitHub token override for private repositories.",
    )

    model_config = {"populate_by_name": True}


class DiscoveryRepository(BaseModel):
    repo_url: str = Field(..., alias="repoUrl")
    owner: str
    repo_name: str = Field(..., alias="repoName")
    visibility: str

    model_config = {"populate_by_name": True}


class DiscoveryDependency(BaseModel):
    group_id: str = Field(..., alias="groupId")
    artifact_id: str = Field(..., alias="artifactId")
    version: Optional[str] = None

    model_config = {"populate_by_name": True}


class DiscoveryFrontend(BaseModel):
    detected: bool
    type: str
    path: Optional[str] = None
    package_manager: Optional[str] = Field(default=None, alias="packageManager")

    model_config = {"populate_by_name": True}


class DiscoveryProject(BaseModel):
    build_tool: str = Field(..., alias="buildTool")
    current_java_version: str = Field(..., alias="currentJavaVersion")
    spring_boot_version: Optional[str] = Field(None, alias="springBootVersion")
    project_type: str = Field(..., alias="projectType")
    multi_module: bool = Field(..., alias="multiModule")
    modules: list[str] = Field(default_factory=list)
    dependencies_count: int = Field(..., alias="dependenciesCount")
    frontend_detected: bool = Field(..., alias="frontendDetected")
    frontend_type: Optional[str] = Field(None, alias="frontendType")

    model_config = {"populate_by_name": True}


class DiscoveryResponse(BaseModel):
    """Success body for ``POST /api/v1/discovery/{jobId}``."""

    job_id: str = Field(..., alias="jobId")
    status: str
    message: str
    repository: DiscoveryRepository
    project: DiscoveryProject
    next_step: str = Field(..., alias="nextStep")

    model_config = {"populate_by_name": True}


class DiscoveryErrorResponse(BaseModel):
    """Error body for a failed discovery attempt."""

    job_id: str = Field(..., alias="jobId")
    status: str
    message: str

    model_config = {"populate_by_name": True}
