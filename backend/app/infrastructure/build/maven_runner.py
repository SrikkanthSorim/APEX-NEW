"""Runs OpenRewrite via the Maven plugin.

Only the ``rewrite:run`` goal is invoked (apply recipes in place). No project
build/verify is run here.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.infrastructure.migration_engine.recipe_mapper import RecipePlan
from app.shared.command_runner import CommandResult, resolve_executable, run_command


class MavenNotAvailableError(RuntimeError):
    pass


class MavenRewriteRunner:
    """Invokes ``rewrite-maven-plugin:run`` in a project directory."""

    def is_available(self) -> bool:
        return resolve_executable("mvn") is not None

    def run(self, project_dir: Path, plan: RecipePlan) -> CommandResult:
        mvn = resolve_executable("mvn")
        if not mvn:
            raise MavenNotAvailableError("Maven (mvn) was not found on PATH.")

        goal = (
            f"org.openrewrite.maven:rewrite-maven-plugin:"
            f"{settings.openrewrite_maven_plugin_version}:run"
        )
        command = [
            mvn,
            "-B",
            "-U",
            goal,
            f"-Drewrite.activeRecipes={plan.active_recipes_csv}",
            f"-Drewrite.recipeArtifactCoordinates={plan.recipe_artifact}",
            "-Drewrite.exportDatatables=false",
        ]
        return run_command(
            command,
            cwd=project_dir,
            timeout=settings.migration_timeout_seconds,
        )
