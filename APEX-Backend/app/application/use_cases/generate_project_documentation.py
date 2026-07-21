"""Generate the header "Docs" feature's project documentation.

Composes data already produced by earlier stages (Connect/Discovery/Migration
Config reports on disk, plus the migration result once a migration has run)
rather than re-analyzing the repository. The full downloadable HTML document
reuses ``GenerateTechnicalDocumentUseCase`` for the repository-analysis
sections and appends migration-strategy sections in matching style.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

from app.application.pipelines.migration_execution_pipeline import MigrationExecutionPipeline
from app.application.use_cases.generate_technical_document import GenerateTechnicalDocumentUseCase
from app.core.exceptions import MigrationJobNotFoundError
from app.infrastructure.persistence.job_repository import JobRepository
from app.schemas.docs_schema import MigrationStrategySection, ProjectDocsResponse
from app.schemas.document_schema import TechnicalDocumentRequest
from app.shared import branding


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


class GenerateProjectDocumentationUseCase:
    def __init__(
        self,
        job_repository: JobRepository | None = None,
        tech_doc_use_case: GenerateTechnicalDocumentUseCase | None = None,
        migration_pipeline: MigrationExecutionPipeline | None = None,
    ) -> None:
        self._job_repository = job_repository or JobRepository()
        self._tech_doc_use_case = tech_doc_use_case or GenerateTechnicalDocumentUseCase()
        self._migration_pipeline = migration_pipeline or MigrationExecutionPipeline()

    def get_structured(self, job_id: str) -> ProjectDocsResponse:
        if not self._job_repository.job_exists(job_id):
            raise MigrationJobNotFoundError()

        connect_report = self._job_repository.read_connect_report(job_id) or {}
        discovery_report = self._job_repository.read_discovery_report(job_id) or {}
        config_report = self._job_repository.read_migration_config_report(job_id) or {}

        frontend = discovery_report.get("frontend")
        strategy = self._build_strategy_section(job_id, config_report)
        has_repository_analysis = self._has_repository_analysis(discovery_report)

        return ProjectDocsResponse(
            job_id=job_id,
            project_name=connect_report.get("repoName"),
            repo_url=connect_report.get("repoUrl"),
            has_repository_analysis=has_repository_analysis,
            detected_java_version=discovery_report.get("currentJavaVersion"),
            target_java_version=strategy.target_java_version or config_report.get("targetJavaVersion"),
            build_tool=discovery_report.get("buildTool") or config_report.get("buildTool"),
            project_type=discovery_report.get("projectType"),
            frameworks=discovery_report.get("frameworks") or [],
            dependencies=discovery_report.get("dependencies") or [],
            modules=discovery_report.get("modules") or [],
            frontend=frontend if isinstance(frontend, dict) else None,
            generated_at=datetime.now(timezone.utc).isoformat(),
            strategy=strategy,
        )

    @staticmethod
    def _has_repository_analysis(discovery_report: dict[str, Any]) -> bool:
        if not discovery_report:
            return False
        return any(
            bool(discovery_report.get(key))
            for key in (
                "currentJavaVersion",
                "buildTool",
                "projectType",
                "frameworks",
                "dependencies",
                "modules",
            )
        )

    def get_html(self, job_id: str) -> dict[str, str]:
        if not self._job_repository.job_exists(job_id):
            raise MigrationJobNotFoundError()

        connect_report = self._job_repository.read_connect_report(job_id) or {}
        config_report = self._job_repository.read_migration_config_report(job_id) or {}
        strategy = self._build_strategy_section(job_id, config_report)

        tech_doc = self._tech_doc_use_case.execute(
            TechnicalDocumentRequest(job_id=job_id, repo_url=connect_report.get("repoUrl"))
        )
        combined_html = self._append_strategy_sections(tech_doc["html"], strategy)
        filename = tech_doc["filename"].replace(
            "-TECHNICAL-DOCUMENT.html", "-PROJECT-DOCUMENTATION.html"
        )
        return {"filename": filename, "html": combined_html}

    def _build_strategy_section(
        self, job_id: str, config_report: dict[str, Any]
    ) -> MigrationStrategySection:
        try:
            detail = self._migration_pipeline.get_detail(job_id)
        except MigrationJobNotFoundError:
            return MigrationStrategySection(
                has_migration_run=False,
                target_java_version=config_report.get("targetJavaVersion"),
                conversion_types=config_report.get("conversionTypes") or [],
            )

        return MigrationStrategySection(
            has_migration_run=True,
            target_java_version=detail.get("target_java_version") or config_report.get("targetJavaVersion"),
            conversion_types=detail.get("conversion_types") or config_report.get("conversionTypes") or [],
            recipes_executed=detail.get("recipes_executed") or [],
            recipe_selection_reasons=detail.get("recipe_selection_reasons") or [],
            build_modernization=detail.get("build_modernization") or [],
            dependency_upgrades=detail.get("dependency_upgrades") or [],
            import_changes=detail.get("import_changes") or [],
            source_changes=detail.get("source_changes") or [],
            retry_attempts=detail.get("retry_attempts") or [],
            build_status=detail.get("build_status"),
            build_success=detail.get("build_success"),
            migration_summary=detail.get("migration_summary"),
        )

    def _append_strategy_sections(self, tech_doc_html: str, strategy: MigrationStrategySection) -> str:
        sections = self._render_strategy_html(strategy)
        if "</main>" in tech_doc_html:
            return tech_doc_html.replace("</main>", f"{sections}</main>")
        return f"{tech_doc_html}<div>{sections}</div>"

    def _render_strategy_html(self, strategy: MigrationStrategySection) -> str:
        if not strategy.has_migration_run:
            return (
                '<section class="page"><div class="page-inner">'
                "<h2>Migration Strategy</h2>"
                '<p class="muted">No migration has been run for this project yet. '
                "Dependency changes, source code changes, and the "
                "migration report will appear here once Start Migration completes.</p>"
                "</div></section>"
            )

        return f"""<section class="page"><div class="page-inner">
      <h2>Migration Strategy</h2>
      {self._table(["Attribute", "Value"], [
          ("Target Java Version", strategy.target_java_version or "Not set"),
          ("Conversion Types", ", ".join(strategy.conversion_types) or "-"),
          ("Build Status", strategy.build_status or "Unknown"),
          ("Build Success", "Yes" if strategy.build_success else "No"),
      ])}
      <h2>Dependency Changes</h2>
      {self._list_or_empty(strategy.dependency_upgrades)}
      <h2>Source Code Changes</h2>
      <h3>Import Changes</h3>
      {self._list_or_empty(strategy.import_changes)}
      <h3>Source File Changes</h3>
      {self._list_or_empty(strategy.source_changes)}
      <h2>Migration Report</h2>
      <p>{_e(branding.sanitize(strategy.migration_summary)) or '<span class="muted">No migration summary available.</span>'}</p>
    </div></section>"""

    def _table(self, headers: list[str], rows: list[tuple[Any, ...]]) -> str:
        head = "".join(f"<th>{_e(header)}</th>" for header in headers)
        body = "".join(
            "<tr>" + "".join(f"<td>{_e(value)}</td>" for value in row) + "</tr>" for row in rows
        )
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    def _list_or_empty(self, items: list[Any]) -> str:
        if not items:
            return '<p class="muted">No data available for this section.</p>'
        rendered = []
        for item in items:
            if isinstance(item, dict):
                text = ", ".join(f"{_e(k)}: {_e(v)}" for k, v in item.items())
            else:
                text = _e(item)
            rendered.append(f"<li>{text}</li>")
        return f"<ul>{''.join(rendered)}</ul>"
