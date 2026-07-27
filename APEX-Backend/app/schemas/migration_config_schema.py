"""Request/response schemas for the Migration Config endpoint.

This stage only *saves* the migration destination + selected options. No repo
creation or push happens here (that's the Start Migration stage).
"""

from typing import Optional

from pydantic import BaseModel, Field

# Destination modes (map to the frontend's three destination cards).
MODE_CREATE_NEW_REPO = "CREATE_NEW_REPO"
MODE_EXISTING_REPO_BRANCH = "EXISTING_REPO_BRANCH"
MODE_LOCAL_FOLDER = "LOCAL_FOLDER"
VALID_MODES = {MODE_CREATE_NEW_REPO, MODE_EXISTING_REPO_BRANCH, MODE_LOCAL_FOLDER}


class MigrationDestination(BaseModel):
    """Where migrated code will eventually be published."""

    mode: str = Field(..., description="CREATE_NEW_REPO | EXISTING_REPO_BRANCH | LOCAL_FOLDER")
    target_owner: Optional[str] = Field(None, alias="targetOwner")
    target_host: Optional[str] = Field(None, alias="targetHost")
    target_repo_name: Optional[str] = Field(None, alias="targetRepoName")
    target_repo_url: Optional[str] = Field(None, alias="targetRepoUrl")
    target_branch: Optional[str] = Field(None, alias="targetBranch")
    local_folder: Optional[str] = Field(None, alias="localFolder")

    model_config = {"populate_by_name": True}


class MigrationConfigOptions(BaseModel):
    """Migration toggles selected on the config page."""

    run_tests: bool = Field(False, alias="runTests")
    use_llm_tests: bool = Field(False, alias="useLlmTests")
    run_sonar: bool = Field(False, alias="runSonar")
    run_fossa: bool = Field(False, alias="runFossa")
    fix_business_logic: bool = Field(False, alias="fixBusinessLogic")

    model_config = {"populate_by_name": True}


class MigrationConfigRequest(BaseModel):
    """Body for ``POST /api/v1/migration-config/{jobId}``."""

    destination: MigrationDestination
    source_repo_url: Optional[str] = Field(None, alias="sourceRepoUrl")
    source_java_version: Optional[str] = Field(None, alias="sourceJavaVersion")
    target_java_version: Optional[str] = Field(None, alias="targetJavaVersion")
    build_tool: Optional[str] = Field(None, alias="buildTool")
    conversion_types: list[str] = Field(default_factory=list, alias="conversionTypes")
    options: MigrationConfigOptions = Field(default_factory=MigrationConfigOptions)

    model_config = {"populate_by_name": True}


class MigrationConfigResponse(BaseModel):
    """Success body for ``POST /api/v1/migration-config/{jobId}``."""

    job_id: str = Field(..., alias="jobId")
    status: str
    message: str
    destination: MigrationDestination
    next_step: str = Field(..., alias="nextStep")

    model_config = {"populate_by_name": True}
