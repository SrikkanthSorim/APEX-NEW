"""Compiles and executes JUnit tests via Gradle, and produces JaCoCo coverage.

Mirrors ``MavenTestRunner``'s public interface exactly (``run_class`` /
``run_suite_with_coverage``) so ``GenerateUnitTestsUseCase``/
``RunUnitTestsUseCase`` can pick either at runtime by ``build_tool`` alone.
Follows the same subprocess pattern as ``BuildValidator``'s Gradle path:
resolve the wrapper (or system Gradle) via ``resolve_gradle_executable``, cap
the JDK to what the wrapper's own Gradle version supports, and share
``GRADLE_USER_HOME`` across jobs so the distribution/dependency caches are
downloaded once, not per job.

Unlike Maven (whose ``jacoco-maven-plugin:VERSION:prepare-agent``/``:report``
goals can be invoked by fully-qualified coordinates on the command line with
zero pom.xml edits), Gradle has no CLI equivalent -- a plugin must be applied
from *somewhere*. The equivalent "never touch the project's own build files"
trick here is an ``--init-script``: it applies the ``jacoco`` plugin and wires
up an XML report for this invocation only, without editing the project's own
``build.gradle``/``settings.gradle`` at all.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from textwrap import dedent

from app.core.config import settings
from app.domain.models.build_result import BuildResult
from app.infrastructure.build.build_log_parser import parse_build_output
from app.infrastructure.java_runtime import build_tool_env, gradle_runtime_major, resolve_gradle_executable
from app.shared.command_runner import run_command


class GradleTestRunner:
    """Runs generated-class-first, then full-suite-with-coverage, per Step 7/9."""

    def is_available(self, project_dir: Path) -> bool:
        return resolve_gradle_executable(project_dir) is not None

    def run_class(self, project_dir: Path, simple_class_name: str, target_major: int | None = None) -> BuildResult:
        """Compile + run a single (typically newly generated) test class first."""
        gradle = resolve_gradle_executable(project_dir)
        if not gradle:
            return BuildResult(
                success=False, tool="gradle", status="FAILED",
                error_lines=["Gradle (wrapper or system) was not found."],
                safe_summary="Gradle (wrapper or system) was not found.",
            )
        command = [gradle, "test", "--tests", f"*.{simple_class_name}", "--continue"]
        runtime_major = gradle_runtime_major(project_dir, target_major)
        return self._run(project_dir, command, runtime_major, settings.unit_test_generated_class_timeout_seconds)

    def run_suite_with_coverage(self, project_dir: Path, target_major: int | None = None) -> BuildResult:
        """Run the full test suite with JaCoCo instrumentation + XML report.

        Applies the ``jacoco`` plugin via a generated ``--init-script`` (never
        edits the project's own ``build.gradle``) and sets ``ignoreFailures``
        plus ``finalizedBy`` so ``jacocoTestReport`` still runs -- and the
        report still gets written -- even when a test fails, mirroring what
        Maven's ``-Dmaven.test.failure.ignore=true`` guarantees.
        """
        gradle = resolve_gradle_executable(project_dir)
        if not gradle:
            return BuildResult(
                success=False, tool="gradle", status="FAILED",
                error_lines=["Gradle (wrapper or system) was not found."],
                safe_summary="Gradle (wrapper or system) was not found.",
            )
        runtime_major = gradle_runtime_major(project_dir, target_major)
        with tempfile.TemporaryDirectory(prefix="jacoco-init-") as tmp:
            init_script = Path(tmp) / "jacoco-init.gradle"
            init_script.write_text(_jacoco_init_script(settings.jacoco_maven_plugin_version), encoding="utf-8")
            command = [gradle, "--init-script", str(init_script), "test", "jacocoTestReport", "--continue"]
            return self._run(project_dir, command, runtime_major, settings.unit_test_timeout_seconds)

    def _run(self, project_dir: Path, command: list[str], target_major: int | None, timeout: float) -> BuildResult:
        started = time.monotonic()
        result = run_command(
            command, cwd=project_dir, timeout=timeout, env=self._gradle_env(project_dir, target_major)
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        parsed = parse_build_output(result.stdout, result.stderr)
        return BuildResult.from_command("gradle", result, parsed, duration_ms)

    @staticmethod
    def _gradle_env(project_dir: Path, target_major: int | None) -> dict[str, str]:
        """Same GRADLE_USER_HOME/java.home sharing as ``BuildValidator``'s
        Gradle path, so this doesn't re-download the Gradle distribution or
        dependencies that a build-validation run already cached."""
        env = build_tool_env(target_major)

        cache_root = project_dir.parent / ".javaapex-gradle"
        gradle_home = settings.gradle_shared_cache_dir
        java_user_home = cache_root / "java-user-home"
        gradle_home.mkdir(parents=True, exist_ok=True)
        java_user_home.mkdir(parents=True, exist_ok=True)

        env["GRADLE_USER_HOME"] = str(gradle_home)
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


def _jacoco_init_script(tool_version: str) -> str:
    return dedent(
        f"""\
        allprojects {{
            apply plugin: 'jacoco'
            jacoco {{
                toolVersion = "{tool_version}"
            }}
            tasks.withType(Test).configureEach {{ Test t ->
                t.ignoreFailures = true
                t.finalizedBy(tasks.withType(JacocoReport))
            }}
            tasks.withType(JacocoReport).configureEach {{ JacocoReport r ->
                try {{
                    r.reports.xml.required.set(true)
                    r.reports.html.required.set(false)
                }} catch (Throwable ignored) {{
                    r.reports.xml.enabled = true
                    r.reports.html.enabled = false
                }}
            }}
        }}
        """
    )
