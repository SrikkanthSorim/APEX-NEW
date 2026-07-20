"""Generate repository-grounded technical specification documents."""

from __future__ import annotations

import html
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.exceptions import CloneFailedError, RepositoryWorkspaceNotFoundError
from app.infrastructure.analyzers.microservice.chunk_builder import build_chunks, classify_role
from app.infrastructure.analyzers.microservice.java_class_scanner import JavaClassInfo, JavaClassScanner
from app.infrastructure.analyzers.project_analyzer import ProjectAnalysis, ProjectAnalyzer
from app.infrastructure.git.repository_cloner import RepositoryCloner
from app.infrastructure.persistence.job_repository import JobRepository
from app.infrastructure.workspace.workspace_paths import WorkspacePaths
from app.schemas.document_schema import TechnicalDocumentRequest
from app.shared import file_utils


@dataclass(frozen=True)
class DocumentClassGroup:
    controllers: list[JavaClassInfo]
    services: list[JavaClassInfo]
    repositories: list[JavaClassInfo]
    entities: list[JavaClassInfo]
    others: list[JavaClassInfo]


class GenerateTechnicalDocumentUseCase:
    def __init__(
        self,
        job_repository: JobRepository | None = None,
        analyzer: ProjectAnalyzer | None = None,
        scanner: JavaClassScanner | None = None,
        cloner: RepositoryCloner | None = None,
    ) -> None:
        self._job_repository = job_repository or JobRepository()
        self._analyzer = analyzer or ProjectAnalyzer()
        self._scanner = scanner or JavaClassScanner()
        self._cloner = cloner or RepositoryCloner()

    def execute(self, request: TechnicalDocumentRequest) -> dict[str, str]:
        repo_root, cleanup = self._resolve_repository_root(request)
        try:
            if repo_root is not None:
                return self._generate_from_repository(repo_root, request)
            return self._generate_from_snapshot(request)
        finally:
            if cleanup is not None:
                file_utils.remove_tree(cleanup)

    def _resolve_repository_root(self, request: TechnicalDocumentRequest) -> tuple[Path | None, Path | None]:
        job_id = (request.job_id or request.migration_job_id or "").strip()
        if job_id:
            paths = WorkspacePaths(job_id)
            if paths.original_repo_dir.is_dir():
                return paths.original_repo_dir, None

        repo_url = self._repo_url(request)
        if not repo_url:
            return None, None
        if repo_url.lower().startswith("local://"):
            return None, None

        clone_id = f"technical-document-{uuid.uuid4().hex}"
        target_dir = settings.storage_dir / "_document-workspaces" / clone_id
        token = (request.github_token or request.token or settings.github_token or "").strip() or None
        self._cloner.clone(repo_url, target_dir, token=token)
        return target_dir, target_dir

    def _generate_from_repository(self, repo_root: Path, request: TechnicalDocumentRequest) -> dict[str, str]:
        analysis = self._analyzer.analyze(repo_root)
        classes = self._scanner.scan(repo_root)
        class_groups = self._group_classes(classes)
        chunks = build_chunks(classes)
        endpoints = self._collect_endpoints(class_groups.controllers)
        tables = self._collect_tables(repo_root, class_groups.entities)

        repo_name = self._project_name(request, analysis)
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        context = {
            "project_name": repo_name,
            "repo_url": self._repo_url(request) or request.source_repo or repo_name,
            "generated_at": generated_at,
            "analysis": analysis,
            "classes": classes,
            "groups": class_groups,
            "chunks": chunks,
            "endpoints": endpoints,
            "tables": tables,
            "request": request,
        }
        html_content = self._render_html(context)
        filename = f"{self._safe_filename(repo_name)}-TECHNICAL-DOCUMENT.html"
        self._save_for_job(request, filename, html_content)
        return {"filename": filename, "html": html_content, "document_type": "TECHNICAL_SPECIFICATION"}

    def _generate_from_snapshot(self, request: TechnicalDocumentRequest) -> dict[str, str]:
        snapshot = request.analysis or {}
        repo_name = self._project_name_from_snapshot(request, snapshot)
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        html_content = self._render_snapshot_html(repo_name, generated_at, request, snapshot)
        filename = f"{self._safe_filename(repo_name)}-TECHNICAL-DOCUMENT.html"
        return {"filename": filename, "html": html_content, "document_type": "TECHNICAL_SPECIFICATION"}

    @staticmethod
    def _repo_url(request: TechnicalDocumentRequest) -> str:
        return (request.repo_url or request.repository_url or request.source_repo_url or "").strip()

    def _project_name(self, request: TechnicalDocumentRequest, analysis: ProjectAnalysis | None = None) -> str:
        if request.source_repo and "/" not in request.source_repo:
            return request.source_repo
        repo_url = self._repo_url(request)
        if repo_url:
            return repo_url.rstrip("/").split("/")[-1].removesuffix(".git") or "repository"
        if analysis and analysis.modules:
            return analysis.modules[0]
        return "repository"

    @staticmethod
    def _project_name_from_snapshot(request: TechnicalDocumentRequest, snapshot: dict[str, Any]) -> str:
        for value in (snapshot.get("name"), snapshot.get("projectName"), request.source_repo):
            if isinstance(value, str) and value.strip():
                return value.strip().split("/")[-1].removesuffix(".git")
        repo_url = GenerateTechnicalDocumentUseCase._repo_url(request)
        return repo_url.rstrip("/").split("/")[-1].removesuffix(".git") if repo_url else "repository"

    @staticmethod
    def _group_classes(classes: list[JavaClassInfo]) -> DocumentClassGroup:
        groups: dict[str, list[JavaClassInfo]] = {
            "controller": [],
            "service": [],
            "repository": [],
            "entity": [],
            "other": [],
        }
        for cls in classes:
            groups[classify_role(cls)].append(cls)
        return DocumentClassGroup(
            controllers=groups["controller"],
            services=groups["service"],
            repositories=groups["repository"],
            entities=groups["entity"],
            others=groups["other"],
        )

    @staticmethod
    def _collect_endpoints(controllers: list[JavaClassInfo]) -> list[dict[str, str]]:
        endpoints: list[dict[str, str]] = []
        for controller in controllers:
            for endpoint in controller.endpoints:
                endpoints.append(
                    {
                        "controller": controller.class_name,
                        "method": endpoint.method.replace("Mapping", "").upper() or "REQUEST",
                        "path": endpoint.path or "/",
                        "file": controller.relative_path,
                    }
                )
        return endpoints

    @staticmethod
    def _collect_tables(repo_root: Path, entities: list[JavaClassInfo]) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        for entity in entities:
            text = file_utils.read_text(repo_root / entity.relative_path)
            table_match = re.search(r"@Table\s*\([^)]*name\s*=\s*\"([^\"]+)\"", text)
            field_names = [
                match.group(2)
                for match in re.finditer(
                    r"(?m)^\s*(?:private|protected|public)\s+(?:final\s+)?([\w<>., ?]+)\s+(\w+)\s*[;=]",
                    text,
                )
                if match.group(2) not in {"serialVersionUID"}
            ]
            tables.append(
                {
                    "model": entity.class_name,
                    "table": table_match.group(1) if table_match else entity.class_name,
                    "fields": field_names[:20],
                    "file": entity.relative_path,
                }
            )
        return tables

    def _render_html(self, context: dict[str, Any]) -> str:
        analysis: ProjectAnalysis = context["analysis"]
        groups: DocumentClassGroup = context["groups"]
        dependencies = [dep.to_dict() for dep in analysis.dependencies]
        stats = {
            "Java files": len(analysis.java_files),
            "Dependencies": len(dependencies),
            "Controllers": len(groups.controllers),
            "Services": len(groups.services),
            "Repositories": len(groups.repositories),
            "Entities": len(groups.entities),
            "Endpoints": len(context["endpoints"]),
            "Modules": len(analysis.modules) or 1,
        }
        recommendations = self._recommendations(analysis, context)

        return self._html_document(
            project_name=context["project_name"],
            repo_url=context["repo_url"],
            generated_at=context["generated_at"],
            summary_rows=[
                ("Java Version", analysis.current_java_version),
                ("Spring Boot Version", analysis.spring_boot_version or "Not detected"),
                ("Build Tool", analysis.build_tool),
                ("Project Type", analysis.project_type),
                ("Module Layout", "Multi-module" if analysis.multi_module else "Single module"),
                ("Frontend", analysis.frontend.type if analysis.frontend.detected else "Not detected"),
            ],
            stats=stats,
            dependencies=dependencies,
            controllers=groups.controllers,
            services=groups.services,
            repositories=groups.repositories,
            entities=groups.entities,
            endpoints=context["endpoints"],
            tables=context["tables"],
            modules=analysis.modules,
            chunks=context["chunks"],
            recommendations=recommendations,
            architecture=self._architecture_overview(analysis, groups),
            flow=self._application_flow(groups, context["endpoints"]),
        )

    def _render_snapshot_html(
        self,
        project_name: str,
        generated_at: str,
        request: TechnicalDocumentRequest,
        snapshot: dict[str, Any],
    ) -> str:
        dependencies = snapshot.get("dependencies") if isinstance(snapshot.get("dependencies"), list) else []
        endpoints = snapshot.get("api_endpoints") if isinstance(snapshot.get("api_endpoints"), list) else []
        stats = {
            "Java files": len(snapshot.get("java_files") or []),
            "Dependencies": len(dependencies),
            "Endpoints": len(endpoints),
        }
        return self._html_document(
            project_name=project_name,
            repo_url=self._repo_url(request) or project_name,
            generated_at=generated_at,
            summary_rows=[
                ("Java Version", snapshot.get("java_version") or request.source_java_version or "Not detected"),
                ("Spring Boot Version", snapshot.get("spring_boot_version") or "Not detected"),
                ("Build Tool", snapshot.get("build_tool") or "Not detected"),
                ("Project Type", snapshot.get("project_type") or "Not detected"),
            ],
            stats=stats,
            dependencies=dependencies,
            controllers=[],
            services=[],
            repositories=[],
            entities=[],
            endpoints=endpoints,
            tables=[],
            modules=[],
            chunks=[],
            recommendations=["Run Discovery before generating the document to include full class, endpoint, and module analysis."],
            architecture="Generated from the available repository analysis snapshot.",
            flow="Application flow requires source scanning. Run Discovery to populate controller and service flow details.",
        )

    def _html_document(
        self,
        *,
        project_name: str,
        repo_url: str,
        generated_at: str,
        summary_rows: list[tuple[str, Any]],
        stats: dict[str, int],
        dependencies: list[Any],
        controllers: list[JavaClassInfo],
        services: list[JavaClassInfo],
        repositories: list[JavaClassInfo],
        entities: list[JavaClassInfo],
        endpoints: list[Any],
        tables: list[dict[str, Any]],
        modules: list[str],
        chunks: list[Any],
        recommendations: list[str],
        architecture: str,
        flow: str,
    ) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{self._e(project_name)} - Technical Specification</title>
<style>
@page {{ size: A4; margin: 0; }}
:root {{ --ink:#1a1a1a; --paper:#fff; --cream:#f5f5f4; --border:#d0d0d0; --muted:#555; --bg:#d4d4d4; --accent:#1a1a2e; --page-w:794px; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:13px/1.75 Consolas, 'DM Mono', monospace; }}
.doc-wrapper {{ padding:48px 0 80px; display:flex; flex-direction:column; align-items:center; }}
.page {{ width:var(--page-w); max-width:calc(100% - 40px); background:var(--paper); margin:0 auto 28px; border-radius:12px; box-shadow:0 6px 40px rgba(0,0,0,.17); page-break-after:always; overflow:hidden; }}
.page-inner {{ padding:50px 60px; }}
.brand {{ display:flex; align-items:center; gap:12px; padding-bottom:18px; border-bottom:2px solid var(--border); margin-bottom:28px; }}
.mark {{ width:40px; height:40px; border:2px solid var(--ink); border-radius:50%; display:grid; place-items:center; font:700 18px Georgia, serif; }}
.brand-name {{ font:800 12px Arial, sans-serif; letter-spacing:.14em; text-transform:uppercase; }}
.doc-type {{ font:700 10px Arial, sans-serif; letter-spacing:.22em; color:var(--muted); text-transform:uppercase; margin-bottom:8px; }}
h1 {{ font:42px/1.1 Georgia, serif; margin:0 0 10px; word-break:break-word; }}
h2 {{ font:800 18px Arial, sans-serif; letter-spacing:.05em; text-transform:uppercase; margin:34px 0 14px; padding-left:12px; border-left:4px solid var(--ink); }}
h3 {{ font:700 14px Arial, sans-serif; margin:20px 0 8px; }}
p {{ margin:0 0 12px; }}
.muted {{ color:var(--muted); }}
.grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:18px 0 8px; }}
.metric {{ border:1px solid var(--border); background:var(--cream); border-radius:8px; padding:12px; }}
.metric b {{ display:block; font-size:20px; line-height:1.1; }}
table {{ width:100%; border-collapse:separate; border-spacing:0; margin:12px 0 18px; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.04); }}
th {{ background:var(--ink); color:#fff; text-align:left; padding:10px 12px; font:700 10px Arial, sans-serif; letter-spacing:.12em; text-transform:uppercase; }}
td {{ padding:10px 12px; border-bottom:1px solid var(--border); vertical-align:top; }}
tr:nth-child(even) td {{ background:var(--cream); }}
.pill {{ display:inline-block; border:1px solid var(--border); border-radius:999px; padding:3px 9px; margin:2px; background:#fafafa; }}
.code {{ background:#111827; color:#d1fae5; border-radius:8px; padding:14px; white-space:pre-wrap; overflow-wrap:anywhere; }}
ul {{ margin:8px 0 16px 22px; padding:0; }}
.footer {{ color:#aaa; font-size:10px; text-transform:uppercase; letter-spacing:.1em; margin-top:28px; }}
@media print {{ body {{ background:#fff; }} .doc-wrapper {{ padding:0; }} .page {{ box-shadow:none; margin:0; border-radius:0; max-width:none; }} }}
</style>
</head>
<body>
<main class="doc-wrapper">
  <section class="page">
    <div class="page-inner">
      <div class="brand"><div class="mark">A</div><div><div class="brand-name">Java Migration Accelerator</div><div class="muted">Repository-grounded source analysis</div></div></div>
      <div class="doc-type">Technical Specification Document</div>
      <h1>{self._e(project_name)}</h1>
      <p class="muted">{self._e(repo_url)}</p>
      <p>Generated: {self._e(generated_at)}</p>
      <div class="grid">{''.join(f'<div class="metric"><b>{value}</b><span>{self._e(label)}</span></div>' for label, value in stats.items())}</div>
      <h2>Project Summary</h2>
      {self._table(["Attribute", "Detected Value"], summary_rows)}
      <h2>Architecture Overview</h2>
      <p>{self._e(architecture)}</p>
      <h2>Application Flow</h2>
      <p>{self._e(flow)}</p>
      <div class="footer">Technical specification - generated from repository analysis</div>
    </div>
  </section>
  <section class="page"><div class="page-inner">
    <h2>Dependencies</h2>
    {self._dependency_table(dependencies)}
    <h2>Controllers</h2>
    {self._class_table(controllers)}
    <h2>Services</h2>
    {self._class_table(services)}
    <h2>Repositories</h2>
    {self._class_table(repositories)}
    <h2>Entities</h2>
    {self._class_table(entities)}
  </div></section>
  <section class="page"><div class="page-inner">
    <h2>APIs and Endpoints</h2>
    {self._endpoint_table(endpoints)}
    <h2>Database Tables and Models</h2>
    {self._table(["Model", "Table", "Fields", "Source"], [(t.get("model"), t.get("table"), ", ".join(t.get("fields") or []), t.get("file")) for t in tables])}
    <h2>Module and Chunk Analysis</h2>
    {self._chunk_table(chunks, modules)}
    <h2>Risks and Recommendations</h2>
    <ul>{''.join(f'<li>{self._e(item)}</li>' for item in recommendations)}</ul>
  </div></section>
</main>
</body>
</html>"""

    def _dependency_table(self, dependencies: list[Any]) -> str:
        rows = []
        for dep in dependencies:
            if isinstance(dep, dict):
                rows.append((dep.get("groupId") or dep.get("group_id"), dep.get("artifactId") or dep.get("artifact_id"), dep.get("version") or dep.get("current_version") or "Managed/unknown"))
        return self._table(["Group", "Artifact", "Version"], rows[:80])

    def _class_table(self, classes: list[JavaClassInfo]) -> str:
        return self._table(
            ["Class", "Package", "Dependencies", "Source"],
            [(c.class_name, c.package or "-", ", ".join(sorted(c.dependencies)) or "-", c.relative_path) for c in classes],
        )

    def _endpoint_table(self, endpoints: list[Any]) -> str:
        rows = []
        for endpoint in endpoints:
            if isinstance(endpoint, dict):
                rows.append((endpoint.get("method") or "-", endpoint.get("path") or "/", endpoint.get("controller") or "-", endpoint.get("file") or "-"))
        return self._table(["Method", "Path", "Controller", "Source"], rows)

    def _chunk_table(self, chunks: list[Any], modules: list[str]) -> str:
        rows = [
            (
                chunk.chunk_name,
                chunk.controller.class_name,
                ", ".join(c.class_name for c in chunk.services) or "-",
                ", ".join(c.class_name for c in chunk.repositories) or "-",
                ", ".join(c.class_name for c in chunk.entities) or "-",
            )
            for chunk in chunks
        ]
        if not rows and modules:
            rows = [(module, "-", "-", "-", "-") for module in modules]
        return self._table(["Chunk/Module", "Controller", "Services", "Repositories", "Entities"], rows)

    def _table(self, headers: list[str], rows: list[tuple[Any, ...]]) -> str:
        if not rows:
            return '<p class="muted">No repository data detected for this section.</p>'
        head = "".join(f"<th>{self._e(header)}</th>" for header in headers)
        body = "".join(
            "<tr>" + "".join(f"<td>{self._e(value)}</td>" for value in row) + "</tr>"
            for row in rows
        )
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    @staticmethod
    def _architecture_overview(analysis: ProjectAnalysis, groups: DocumentClassGroup) -> str:
        layers = []
        if groups.controllers:
            layers.append("web/API controllers")
        if groups.services:
            layers.append("service layer")
        if groups.repositories:
            layers.append("repository/data access layer")
        if groups.entities:
            layers.append("domain entity layer")
        layer_text = ", ".join(layers) if layers else "source modules detected by the repository scan"
        module_text = "multi-module" if analysis.multi_module else "single-module"
        return f"{analysis.project_type} application using {analysis.build_tool} with a {module_text} layout and {layer_text}."

    @staticmethod
    def _application_flow(groups: DocumentClassGroup, endpoints: list[dict[str, str]]) -> str:
        if endpoints and groups.services and groups.repositories:
            return "HTTP requests enter controller endpoints, delegate business work to services, and persist or query data through repositories and entities."
        if endpoints and groups.services:
            return "HTTP requests enter controller endpoints and delegate business work to services."
        if endpoints:
            return "HTTP requests enter controller endpoints detected in the source code."
        return "No REST endpoint flow was detected in the scanned Java source files."

    @staticmethod
    def _recommendations(analysis: ProjectAnalysis, context: dict[str, Any]) -> list[str]:
        recommendations: list[str] = []
        if analysis.current_java_version.upper() == "UNKNOWN":
            recommendations.append("Declare the Java version explicitly in the build file to make migrations reproducible.")
        if not analysis.has_tests:
            recommendations.append("Add or expand automated tests before migration because no src/test layout was detected.")
        if len(context["endpoints"]) == 0:
            recommendations.append("No REST endpoints were detected; verify whether this project is a library, batch app, or uses non-Spring routing.")
        if len(context["tables"]) == 0:
            recommendations.append("No JPA/Mongo entities were detected; confirm persistence boundaries manually if the application uses external data stores.")
        if analysis.dependency_count > 40:
            recommendations.append("Review dependency versions and remove unused libraries before modernization to reduce upgrade risk.")
        if not recommendations:
            recommendations.append("Repository structure is clear enough for a standard Java migration assessment. Validate build and test coverage before execution.")
        return recommendations

    def _save_for_job(self, request: TechnicalDocumentRequest, filename: str, html_content: str) -> None:
        job_id = (request.job_id or request.migration_job_id or "").strip()
        if not job_id:
            return
        paths = WorkspacePaths(job_id)
        paths.reports_dir.mkdir(parents=True, exist_ok=True)
        (paths.reports_dir / filename).write_text(html_content, encoding="utf-8")

    @staticmethod
    def _safe_filename(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
        return (cleaned or "repository").upper()

    @staticmethod
    def _e(value: Any) -> str:
        return html.escape("" if value is None else str(value))
