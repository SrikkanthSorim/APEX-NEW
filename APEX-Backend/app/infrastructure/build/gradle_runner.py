"""Runs OpenRewrite on a Gradle project via an init script + ``rewriteRun``.

The init script applies the OpenRewrite Gradle plugin, points it at a
generated declarative recipe YAML (``rewrite.configFile``), and activates that
single composite recipe -- without modifying the project's build files. This
lets parameterized recipes (exact Java version, dependency GAVs, dynamic
version patterns) run without hardcoding any version number in this codebase.
Prefers the project's ``gradlew`` wrapper (respects the project's Gradle
version); falls back to a system ``gradle``.

Gradle support is best-effort: if the OpenRewrite Gradle plugin is incompatible
with the project's Gradle version, the run fails and is reported as such.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import settings
from app.infrastructure.java_runtime import build_tool_env, resolve_gradle_executable
from app.infrastructure.migration_engine.recipe_mapper import RecipePlan
from app.shared.command_runner import CommandResult, run_command


class GradleNotAvailableError(RuntimeError):
    pass


class GradleRewriteRunner:
    def is_available(self, project_dir: Path) -> bool:
        return self._resolve_gradle(project_dir) is not None

    def run(self, project_dir: Path, plan: RecipePlan, target_major: int | None = None) -> CommandResult:
        gradle = self._resolve_gradle(project_dir)
        if not gradle:
            raise GradleNotAvailableError("Gradle (wrapper or system) was not found.")

        run_id = uuid.uuid4().hex
        config_path = project_dir / f".javaapex-rewrite-{run_id}.yml"
        config_path.write_text(plan.to_declarative_yaml(), encoding="utf-8")
        init_script = self._write_init_script(project_dir, plan, config_path, run_id)
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
                env=build_tool_env(target_major),
            )
        finally:
            for temp_file in (init_script, config_path):
                try:
                    temp_file.unlink()
                except OSError:
                    pass

    # -- helpers ------------------------------------------------------------- #

    @staticmethod
    def _resolve_gradle(project_dir: Path) -> str | None:
        return resolve_gradle_executable(project_dir)

    def _write_init_script(self, project_dir: Path, plan: RecipePlan, config_path: Path, run_id: str) -> Path:
        artifacts = "\n".join(
            f'        rewrite("{artifact}")' for artifact in plan.recipe_artifacts
        )
        config_path_gradle = str(config_path).replace("\\", "\\\\")
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
{artifacts}
    }}
    afterEvaluate {{
        rewrite {{
            configFile = file("{config_path_gradle}")
            activeRecipe("{plan.declarative_recipe_name}")
        }}
    }}
}}
"""
        path = project_dir / f".javaapex-rewrite-init-{run_id}.gradle"
        path.write_text(content, encoding="utf-8")
        return path
