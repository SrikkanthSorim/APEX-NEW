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


class DiscoverySpringBootConversion(BaseModel):
    """Spring -> Spring Boot conversion eligibility, computed from the real
    cloned-and-analyzed repository (never from the URL, repo name, or mock
    data). Drives whether the frontend's conversion card is enabled.
    """

    repository_analyzed: bool = Field(..., alias="repositoryAnalyzed")
    java_migration_eligible: bool = Field(..., alias="javaMigrationEligible")
    java_migration_reason: str = Field(..., alias="javaMigrationReason")
    spring_detected: bool = Field(..., alias="springDetected")
    spring_boot_detected: bool = Field(..., alias="springBootDetected")
    spring_version: Optional[str] = Field(None, alias="springVersion")
    spring_boot_version: Optional[str] = Field(None, alias="springBootVersion")
    build_tool: str = Field(..., alias="buildTool")
    spring_boot_conversion_eligible: bool = Field(..., alias="springBootConversionEligible")
    spring_boot_upgrade_eligible: bool = Field(..., alias="springBootUpgradeEligible")
    eligibility_reason: str = Field(..., alias="eligibilityReason")

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
    spring_framework_version: Optional[str] = Field(None, alias="springFrameworkVersion")
    spring_entry_class: Optional[str] = Field(None, alias="springEntryClass")
    java_migration_eligible: bool = Field(..., alias="javaMigrationEligible")
    java_migration_reason: str = Field(..., alias="javaMigrationReason")
    spring_detected: bool = Field(..., alias="springDetected")
    spring_boot_detected: bool = Field(..., alias="springBootDetected")
    spring_boot_conversion_eligible: bool = Field(..., alias="springBootConversionEligible")
    spring_boot_upgrade_eligible: bool = Field(..., alias="springBootUpgradeEligible")
    eligibility_reason: str = Field(..., alias="eligibilityReason")
    spring_boot_conversion: Optional[DiscoverySpringBootConversion] = Field(
        None, alias="springBootConversion"
    )

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


class RepoFileEntryResponse(BaseModel):
    """One folder/file entry in a repository listing."""

    name: str
    path: str
    type: str
    size: int
    url: str = ""


class RepoFilesResponse(BaseModel):
    """Success body for ``GET /api/v1/discovery/{jobId}/files``."""

    job_id: str = Field(..., alias="jobId")
    path: str
    files: list[RepoFileEntryResponse]

    model_config = {"populate_by_name": True}


class RepoFileContentResponse(BaseModel):
    """Success body for ``GET /api/v1/discovery/{jobId}/file``."""

    job_id: str = Field(..., alias="jobId")
    file_path: str = Field(..., alias="filePath")
    content: str
    size: int

    model_config = {"populate_by_name": True}
