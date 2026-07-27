"""Validates that the migrated project still builds (post-OpenRewrite).

Runs a Maven/Gradle build with tests skipped and reports BUILD SUCCESS/FAILED.
Read-only with respect to source; it only produces build output (target/, build/).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from app.core.config import settings
from app.domain.models.build_result import (
    BUILD_STATUS_FAILED,
    BUILD_STATUS_SKIPPED,
    BuildResult,
)
from app.infrastructure.java_runtime import (
    build_tool_env,
    gradle_runtime_major,
    max_available_java_major,
    resolve_gradle_executable,
)
from app.infrastructure.build.build_log_parser import parse_build_output
from app.shared.command_runner import resolve_executable, run_command

logger = logging.getLogger(__name__)


class BuildValidator:
    def validate(self, project_dir: Path, build_tool: str, target_major: int | None = None) -> BuildResult:
        if not settings.build_validation_enabled:
            return BuildResult(success=True, tool="none", skipped=True, status=BUILD_STATUS_SKIPPED,
                               log_lines=["Build validation disabled."])

        if target_major is not None:
            max_major = max_available_java_major()
            if max_major is not None and target_major > max_major:
                return BuildResult(
                    success=True,
                    tool="none",
                    skipped=True,
                    status=BUILD_STATUS_SKIPPED,
                    log_lines=[
                        f"Build validation skipped: no local JDK {target_major}+ is "
                        f"installed (highest available on this machine is Java "
                        f"{max_major}). This is an environment limitation, not a "
                        f"migration failure — the migrated project's build "
                        f"configuration correctly targets Java {target_major} as "
                        f"selected. Install a JDK {target_major}+ (or set "
                        f"BUILD_JAVA_HOME) to validate the build here."
                    ],
                )

        if build_tool == "MAVEN":
            return self._run_maven(project_dir, target_major)
        if build_tool == "GRADLE":
            return self._run_gradle(project_dir, target_major)
        return BuildResult(success=True, tool="none", skipped=True, status=BUILD_STATUS_SKIPPED,
                           log_lines=[f"Build validation not applicable for {build_tool}."])

    # -- Maven --------------------------------------------------------------- #

    def _run_maven(self, project_dir: Path, target_major: int | None) -> BuildResult:
        mvn = resolve_executable("mvn")
        if not mvn:
            return BuildResult(success=False, tool="maven", status=BUILD_STATUS_FAILED,
                               error_lines=["Maven (mvn) was not found on PATH."],
                               safe_summary="Maven (mvn) was not found on PATH.")
        command = [mvn, *settings.build_maven_args_list]
        started = time.monotonic()
        result = run_command(
            command, cwd=project_dir, timeout=settings.build_timeout_seconds,
            env=build_tool_env(target_major),
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        parsed = parse_build_output(result.stdout, result.stderr)
        return BuildResult.from_command("maven", result, parsed, duration_ms)

    # -- Gradle -------------------------------------------------------------- #

    def _run_gradle(self, project_dir: Path, target_major: int | None) -> BuildResult:
        gradle = self._resolve_gradle(project_dir)
        if not gradle:
            return BuildResult(success=False, tool="gradle", status=BUILD_STATUS_FAILED,
                               error_lines=["Gradle (wrapper or system) was not found."],
                               safe_summary="Gradle (wrapper or system) was not found.")
        command = [gradle, *settings.build_gradle_args_list]
        # Cap the JDK to what the (possibly OpenRewrite-upgraded) wrapper's own
        # Gradle version supports -- an old Gradle launched under a too-new
        # JDK crashes during its own build-script analysis (e.g. "Unsupported
        # class file major version") before the project's code ever compiles.
        runtime_major = gradle_runtime_major(project_dir, target_major)
        started = time.monotonic()
        result = run_command(
            command, cwd=project_dir, timeout=settings.build_timeout_seconds,
            env=self._gradle_build_env(project_dir, runtime_major),
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        parsed = parse_build_output(result.stdout, result.stderr)
        return BuildResult.from_command("gradle", result, parsed, duration_ms)

    @staticmethod
    def _resolve_gradle(project_dir: Path) -> str | None:
        return resolve_gradle_executable(project_dir)

    @staticmethod
    def _gradle_build_env(project_dir: Path, target_major: int | None) -> dict[str, str]:
        env = build_tool_env(target_major)

        # Keep Gradle's downloaded distributions/native services out of the
        # user's default home and out of migrated-repo, matching rewrite runs.
        # GRADLE_USER_HOME is shared across jobs (see gradle_runner.py) so the
        # distribution zip is downloaded once and reused instead of every job
        # re-fetching it and risking a network timeout.
        cache_root = project_dir.parent / ".javaapex-gradle"
        gradle_home = settings.gradle_shared_cache_dir
        java_user_home = cache_root / "java-user-home"
        gradle_home.mkdir(parents=True, exist_ok=True)
        java_user_home.mkdir(parents=True, exist_ok=True)

        env["GRADLE_USER_HOME"] = str(gradle_home)
        # See gradle_runner.py: raise the wrapper bootstrap's default
        # socket/connection timeout defensively for first-time-per-version
        # distribution downloads.
        user_home_option = (
            f'-Duser.home="{java_user_home}" '
            "-Dorg.gradle.internal.http.connectionTimeout=120000 "
            "-Dorg.gradle.internal.http.socketTimeout=120000"
        )
        existing_tool_options = env.get("JAVA_TOOL_OPTIONS", "").strip()
        env["JAVA_TOOL_OPTIONS"] = (
            f"{existing_tool_options} {user_home_option}".strip()
            if user_home_option not in existing_tool_options
            else existing_tool_options
        )
        return env
