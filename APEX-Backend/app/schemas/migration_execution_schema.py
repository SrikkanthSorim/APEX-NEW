"""Request schema for the Start Migration endpoint.

Permissive on purpose: the frontend sends the full legacy ``MigrationRequest``
(many fields). We only need a few; the rest are accepted and ignored. The saved
migration-config/discovery reports are the source of truth for the destination
and versions.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class MigrationStartRequest(BaseModel):
    source_repo_url: Optional[str] = None
    target_java_version: Optional[str] = None
    source_java_version: Optional[str] = None
    build_tool: Optional[str] = None
    conversion_types: Optional[list[str]] = None

    # Accept (and ignore) any additional legacy fields the frontend sends.
    model_config = {"extra": "allow"}


class MigrationPreviewRequest(BaseModel):
    source_repo_url: str = ""
    target_repo_name: str = ""
    migration_approach: Optional[str] = None
    platform: str = "github"
    source_java_version: str = ""
    target_java_version: str = ""
    build_tool: Optional[str] = None
    conversion_types: list[str] = Field(default_factory=list)
    run_tests: bool = False
    run_sonar: bool = False
    run_fossa: bool = False
    fix_business_logic: bool = False

    model_config = {"extra": "allow"}


class PreviewFileChange(BaseModel):
    type: str
    pattern: Optional[str] = None
    replacement: Optional[str] = None
    description: str
    occurrences: int = 1


class PreviewFileDiff(BaseModel):
    file_path: str
    diff: str
    change_count: int


class MigrationPreviewResponse(BaseModel):
    repository: str
    platform: str
    source_version: str
    target_version: str
    conversions: list[str]
    business_logic_fixes: bool
    summary: dict[str, int]
    changes: dict[str, Any]
    file_diffs: list[PreviewFileDiff]
