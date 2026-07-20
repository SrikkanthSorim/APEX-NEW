"""Runs OpenRewrite via the Maven plugin.

Only the non-forking ``rewrite:runNoFork`` goal is invoked (apply recipes in
place). This avoids Maven compiling the source project before OpenRewrite has a
chance to update incompatible build/dependency metadata; the separate build
validation phase compiles/packages the migrated project afterward. Recipes are
supplied as a generated declarative recipe YAML (``rewrite.configLocation``)
rather than a flat CSV of zero-arg recipe names, so parameterized recipes
(exact Java version, dependency GAVs, dynamic version patterns) can be
activated without hardcoding any version number in this codebase.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import settings
from app.infrastructure.java_runtime import build_tool_env
from app.infrastructure.migration_engine.recipe_mapper import RecipePlan
from app.shared.command_runner import CommandResult, resolve_executable, run_command


class MavenNotAvailableError(RuntimeError):
    pass


class MavenRewriteRunner:
    """Invokes ``rewrite-maven-plugin:runNoFork`` in a project directory."""

    def is_available(self) -> bool:
        return resolve_executable("mvn") is not None

    def run(self, project_dir: Path, plan: RecipePlan, target_major: int | None = None) -> CommandResult:
        mvn = resolve_executable("mvn")
        if not mvn:
            raise MavenNotAvailableError("Maven (mvn) was not found on PATH.")

        config_path = (project_dir / f".javaapex-rewrite-{uuid.uuid4().hex}.yml").resolve()
        config_path.write_text(plan.to_declarative_yaml(), encoding="utf-8")
        try:
            goal = (
                f"org.openrewrite.maven:rewrite-maven-plugin:"
                f"{settings.openrewrite_maven_plugin_version}:runNoFork"
            )
            command = [
                mvn,
                "-B",
                "-U",
                goal,
                f"-Drewrite.configLocation={config_path}",
                f"-Drewrite.activeRecipes={plan.declarative_recipe_name}",
                f"-Drewrite.recipeArtifactCoordinates={plan.recipe_artifact}",
                "-Drewrite.exportDatatables=false",
            ]
            return run_command(
                command,
                cwd=project_dir,
                timeout=settings.migration_timeout_seconds,
                env=build_tool_env(target_major),
            )
        finally:
            try:
                config_path.unlink()
            except OSError:
                pass
