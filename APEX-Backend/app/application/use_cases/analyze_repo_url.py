"""Analyze a repository by URL (pre-clone), without a persisted migration job.

Clones the repo into a throwaway temp workspace, runs the same Discovery
detectors used by the job-based flow, maps the result to the frontend-facing
snake_case ``RepoAnalysis`` shape, and always cleans up the temp clone.

Used by ``GET /api/github/analyze-url`` for the wizard's no-jobId path.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.application.use_cases.connect_repository import parse_github_url
from app.core.config import settings
from app.infrastructure.analyzers.project_analyzer import ProjectAnalysis, ProjectAnalyzer
from app.infrastructure.git.repository_cloner import RepositoryCloner
from app.shared import file_utils

logger = logging.getLogger(__name__)


class AnalyzeRepoUrlUseCase:
    def __init__(
        self,
        cloner: RepositoryCloner | None = None,
        analyzer: ProjectAnalyzer | None = None,
    ) -> None:
        self._cloner = cloner or RepositoryCloner()
        self._analyzer = analyzer or ProjectAnalyzer()

    def execute(self, repo_url: str, token: str | None) -> dict[str, Any]:
        """Return ``{repo_url, owner, repo, analysis}`` for the given repository URL.

        Synchronous/CPU- and IO-bound (git clone + on-disk analysis); async
        callers should invoke via ``run_in_threadpool``.
        """
        parsed = parse_github_url(repo_url)

        workspace = settings.storage_dir / "_analyze-workspaces" / f"analyze-{uuid4().hex}"
        try:
            self._cloner.clone(repo_url, workspace, token=(token or "").strip() or None)
            analysis = self._analyzer.analyze(workspace)
            return {
                "repo_url": repo_url,
                "owner": parsed.owner,
                "repo": parsed.repo,
                "analysis": _to_repo_analysis(parsed.owner, parsed.repo, analysis),
            }
        finally:
            file_utils.remove_tree(workspace)


def _normalize_build_tool(build_tool: str | None) -> str | None:
    value = (build_tool or "").upper()
    if value == "MAVEN":
        return "maven"
    if value == "GRADLE":
        return "gradle"
    return None


def _normalize_java_version(version: str | None) -> str | None:
    value = (version or "").strip()
    return value if value and value.upper() != "UNKNOWN" else None


def _to_repo_analysis(owner: str, repo: str, analysis: ProjectAnalysis) -> dict[str, Any]:
    """Map ``ProjectAnalysis`` to the frontend ``RepoAnalysis`` (snake_case).

    Mirrors ``mapDiscoveryToRepoAnalysis`` in the frontend so the wizard reads a
    consistent shape regardless of which analysis path produced it.
    """
    java_version = _normalize_java_version(analysis.current_java_version)
    dependencies = [
        {
            "group_id": dep.group_id,
            "artifact_id": dep.artifact_id,
            "current_version": dep.version or "",
            "new_version": None,
            "status": "detected",
        }
        for dep in analysis.dependencies
    ]
    return {
        "name": repo,
        "full_name": f"{owner}/{repo}",
        "default_branch": "main",
        "language": "Java",
        "build_tool": _normalize_build_tool(analysis.build_tool),
        "java_version": java_version,
        "java_version_from_build": java_version,
        "java_files": list(analysis.java_files),
        "has_tests": bool(analysis.has_tests),
        "dependencies": dependencies,
        "api_endpoints": [],
        "detected_frameworks": [],
        "structure": {
            "has_pom_xml": bool(analysis.has_pom_xml),
            "has_build_gradle": bool(analysis.has_build_gradle),
            "has_build_gradle_kts": bool(analysis.has_build_gradle_kts),
            "has_src_main": bool(analysis.has_src_main),
            "has_src_test": bool(analysis.has_src_test),
        },
    }
