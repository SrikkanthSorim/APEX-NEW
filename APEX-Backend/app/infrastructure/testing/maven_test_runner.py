"""Compiles and executes JUnit tests via Maven, and produces JaCoCo coverage.

Follows the exact subprocess pattern already used by ``BuildValidator``/
``MavenRewriteRunner``: resolve ``mvn`` from PATH, run via
``app.shared.command_runner.run_command`` (never ``shell=True``), classify
the outcome from the real exit code/timeout -- never by scanning stdout for
"BUILD SUCCESS" text.
"""

from __future__ import annotations

import time
from pathlib import Path

from app.core.config import settings
from app.domain.models.build_result import BuildResult
from app.infrastructure.build.build_log_parser import parse_build_output
from app.infrastructure.java_runtime import build_tool_env
from app.shared.command_runner import resolve_executable, run_command


class MavenTestRunner:
    """Runs generated-class-first, then full-suite-with-coverage, per Step 7/9."""

    def is_available(self) -> bool:
        return resolve_executable("mvn") is not None

    def run_class(self, project_dir: Path, simple_class_name: str, target_major: int | None = None) -> BuildResult:
        """Compile + run a single (typically newly generated) test class first."""
        mvn = resolve_executable("mvn")
        if not mvn:
            return BuildResult(
                success=False, tool="maven", status="FAILED",
                error_lines=["Maven (mvn) was not found on PATH."],
                safe_summary="Maven (mvn) was not found on PATH.",
            )
        command = [mvn, "-B", f"-Dtest={simple_class_name}", "-DfailIfNoTests=false", "test"]
        return self._run(project_dir, command, target_major, settings.unit_test_generated_class_timeout_seconds)

    def run_suite_with_coverage(self, project_dir: Path, target_major: int | None = None) -> BuildResult:
        """Run the full test suite with JaCoCo instrumentation + XML/HTML report.

        Uses the standard CLI-only JaCoCo technique: `prepare-agent` sets the
        Maven `argLine` property that Surefire consumes by default for the
        forked test JVM, so no pom.xml edits are required for the common
        case. `-Dmaven.test.failure.ignore=true` lets Surefire/JaCoCo still
        produce their reports when a test genuinely fails, instead of
        aborting the build before coverage is written.
        """
        mvn = resolve_executable("mvn")
        if not mvn:
            return BuildResult(
                success=False, tool="maven", status="FAILED",
                error_lines=["Maven (mvn) was not found on PATH."],
                safe_summary="Maven (mvn) was not found on PATH.",
            )
        plugin = f"org.jacoco:jacoco-maven-plugin:{settings.jacoco_maven_plugin_version}"
        command = [
            mvn, "-B",
            f"{plugin}:prepare-agent",
            "test",
            f"{plugin}:report",
            "-Dmaven.test.failure.ignore=true",
        ]
        return self._run(project_dir, command, target_major, settings.unit_test_timeout_seconds)

    @staticmethod
    def _run(project_dir: Path, command: list[str], target_major: int | None, timeout: float) -> BuildResult:
        started = time.monotonic()
        result = run_command(command, cwd=project_dir, timeout=timeout, env=build_tool_env(target_major))
        duration_ms = int((time.monotonic() - started) * 1000)
        parsed = parse_build_output(result.stdout, result.stderr)
        return BuildResult.from_command("maven", result, parsed, duration_ms)
