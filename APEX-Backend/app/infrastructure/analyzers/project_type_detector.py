"""Classifies the project type from its dependencies and layout."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from app.infrastructure.analyzers.dependency_analyzer import Dependency
from app.shared import file_utils

SPRING_BOOT = "SPRING_BOOT"
SPRING_MVC = "SPRING_MVC"
SERVLET_JSP = "SERVLET_JSP"
PLAIN_JAVA = "PLAIN_JAVA"
UNKNOWN = "UNKNOWN"


class ProjectTypeDetector:
    def detect(
        self,
        root: Path,
        build_tool_supported: bool,
        spring_boot_version: str | None,
        dependencies: Iterable[Dependency],
        *,
        spring_boot_signal: bool = False,
    ) -> str:
        deps = list(dependencies)

        if (
            spring_boot_version
            or spring_boot_signal
            or self._has(deps, group="org.springframework.boot")
        ):
            return SPRING_BOOT

        if self._has(deps, artifact_contains="spring-webmvc") or self._has(
            deps, artifact_contains="spring-web"
        ):
            return SPRING_MVC

        if self._is_servlet_jsp(root, deps):
            return SERVLET_JSP

        if build_tool_supported:
            return PLAIN_JAVA

        return UNKNOWN

    # -- helpers ------------------------------------------------------------- #

    def _is_servlet_jsp(self, root: Path, deps: list[Dependency]) -> bool:
        if file_utils.exists(root, "src", "main", "webapp"):
            return True
        if file_utils.exists(root, "src", "main", "webapp", "WEB-INF", "web.xml"):
            return True
        if self._has(deps, artifact_contains="servlet-api") or self._has(
            deps, artifact_contains="javax.servlet"
        ):
            return True
        if file_utils.count_files(root, ".jsp", limit=1) > 0:
            return True
        return False

    @staticmethod
    def _has(
        deps: list[Dependency],
        *,
        group: str | None = None,
        artifact_contains: str | None = None,
    ) -> bool:
        for dep in deps:
            if group and dep.group_id == group:
                return True
            if artifact_contains and artifact_contains in (dep.artifact_id or ""):
                return True
        return False
