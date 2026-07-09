"""Runs OpenRewrite on a Gradle project via an init script + ``rewriteRun``.

The init script applies the OpenRewrite Gradle plugin and configures the active
recipes without modifying the project's build files. Prefers the project's
``gradlew`` wrapper (respects the project's Gradle version); falls back to a
system ``gradle``.

Gradle support is best-effort: if the OpenRewrite Gradle plugin is incompatible
with the project's Gradle version, the run fails and is reported as such.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.core.config import settings
from app.infrastructure.migration_engine.recipe_mapper import RecipePlan
from app.shared.command_runner import CommandResult, resolve_executable, run_command


class GradleNotAvailableError(RuntimeError):
    pass


class GradleRewriteRunner:
    def is_available(self, project_dir: Path) -> bool:
        return self._resolve_gradle(project_dir) is not None

    def run(self, project_dir: Path, plan: RecipePlan) -> CommandResult:
        gradle = self._resolve_gradle(project_dir)
        if not gradle:
            raise GradleNotAvailableError("Gradle (wrapper or system) was not found.")

        init_script = self._write_init_script(plan)
        try:
            command = [
                gradle,
                "--init-script",
                str(init_script),
                "rewriteRun",
                "--no-daemon",
                "--stacktrace",
            ]
            return run_command(
                command,
                cwd=project_dir,
                timeout=settings.migration_timeout_seconds,
            )
        finally:
            try:
                init_script.unlink()
            except OSError:
                pass

    # -- helpers ------------------------------------------------------------- #

    @staticmethod
    def _resolve_gradle(project_dir: Path) -> str | None:
        wrapper = project_dir / ("gradlew.bat" if os.name == "nt" else "gradlew")
        if wrapper.is_file():
            return str(wrapper)
        return resolve_executable("gradle")

    def _write_init_script(self, plan: RecipePlan) -> Path:
        active = "\n".join(
            f'            activeRecipe("{recipe}")' for recipe in plan.active_recipes
        )
        content = f"""\
initscript {{
    repositories {{
        gradlePluginPortal()
        mavenCentral()
    }}
    dependencies {{
        classpath("org.openrewrite:plugin:{settings.openrewrite_gradle_plugin_version}")
    }}
}}

allprojects {{
    apply plugin: org.openrewrite.gradle.RewritePlugin
    dependencies {{
        rewrite("{plan.recipe_artifact}")
    }}
    afterEvaluate {{
        rewrite {{
{active}
        }}
    }}
}}
"""
        fd, name = tempfile.mkstemp(suffix=".gradle", prefix="rewrite-init-")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        return Path(name)
