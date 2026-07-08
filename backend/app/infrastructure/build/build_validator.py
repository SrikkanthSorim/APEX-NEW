"""Validates that the migrated project still builds (post-OpenRewrite).

Runs a Maven/Gradle build with tests skipped and reports BUILD SUCCESS/FAILED.
Read-only with respect to source; it only produces build output (target/, build/).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.core.config import settings
from app.domain.models.build_result import BuildResult
from app.infrastructure.build.build_log_parser import parse_build_output
from app.shared.command_runner import resolve_executable, run_command

logger = logging.getLogger(__name__)


class BuildValidator:
    def validate(self, project_dir: Path, build_tool: str) -> BuildResult:
        if not settings.build_validation_enabled:
            return BuildResult(success=True, tool="none", skipped=True,
                               log_lines=["Build validation disabled."])

        if build_tool == "MAVEN":
            return self._run_maven(project_dir)
        if build_tool == "GRADLE":
            return self._run_gradle(project_dir)
        return BuildResult(success=True, tool="none", skipped=True,
                           log_lines=[f"Build validation not applicable for {build_tool}."])

    # -- Maven --------------------------------------------------------------- #

    def _run_maven(self, project_dir: Path) -> BuildResult:
        mvn = resolve_executable("mvn")
        if not mvn:
            return BuildResult(success=False, tool="maven",
                               error_lines=["Maven (mvn) was not found on PATH."])
        command = [mvn, *settings.build_maven_args_list]
        result = run_command(command, cwd=project_dir, timeout=settings.build_timeout_seconds)
        parsed = parse_build_output(result.stdout, result.stderr)
        return BuildResult(
            success=result.succeeded,
            tool="maven",
            log_lines=parsed.lines,
            error_lines=parsed.error_lines,
        )

    # -- Gradle -------------------------------------------------------------- #

    def _run_gradle(self, project_dir: Path) -> BuildResult:
        gradle = self._resolve_gradle(project_dir)
        if not gradle:
            return BuildResult(success=False, tool="gradle",
                               error_lines=["Gradle (wrapper or system) was not found."])
        command = [gradle, *settings.build_gradle_args_list]
        result = run_command(command, cwd=project_dir, timeout=settings.build_timeout_seconds)
        parsed = parse_build_output(result.stdout, result.stderr)
        return BuildResult(
            success=result.succeeded,
            tool="gradle",
            log_lines=parsed.lines,
            error_lines=parsed.error_lines,
        )

    @staticmethod
    def _resolve_gradle(project_dir: Path) -> str | None:
        wrapper = project_dir / ("gradlew.bat" if os.name == "nt" else "gradlew")
        if wrapper.is_file():
            return str(wrapper)
        return resolve_executable("gradle")
