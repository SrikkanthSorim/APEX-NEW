"""Schemas for the header "Docs" feature — aggregated project documentation."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class MigrationStrategySection(BaseModel):
    """Strategy/execution facts, sourced from the migration result when available."""

    target_java_version: Optional[str] = None
    migration_approach: Optional[str] = None
    conversion_types: list[str] = Field(default_factory=list)
    recipes_executed: list[Any] = Field(default_factory=list)
    recipe_selection_reasons: list[Any] = Field(default_factory=list)
    build_modernization: list[Any] = Field(default_factory=list)
    dependency_upgrades: list[Any] = Field(default_factory=list)
    import_changes: list[Any] = Field(default_factory=list)
    source_changes: list[Any] = Field(default_factory=list)
    retry_attempts: list[Any] = Field(default_factory=list)
    build_status: Optional[str] = None
    build_success: Optional[bool] = None
    migration_summary: Optional[str] = None
    has_migration_run: bool = False


class ProjectDocsResponse(BaseModel):
    """Structured payload rendered by the Docs drawer."""

    job_id: str
    project_name: Optional[str] = None
    repo_url: Optional[str] = None
    has_repository_analysis: bool = False
    detected_java_version: Optional[str] = None
    target_java_version: Optional[str] = None
    build_tool: Optional[str] = None
    project_type: Optional[str] = None
    frameworks: list[str] = Field(default_factory=list)
    dependencies: list[Any] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    frontend: Optional[dict[str, Any]] = None
    generated_at: str
    strategy: MigrationStrategySection


class ProjectDocsHtmlResponse(BaseModel):
    """Full downloadable/printable HTML document."""

    job_id: str
    filename: str
    html: str
