"""Orchestrates the actual code migration on the migrated-repo.

Resolves the project directory, builds the recipe plan, dispatches to the Maven
or Gradle OpenRewrite runner, and (if that fails) applies the internal fallback
so a meaningful result can still be published. Never touches original-repo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.infrastructure.build.gradle_runner import GradleRewriteRunner
from app.infrastructure.build.gradle_wrapper_upgrader import GradleWrapperUpgrader
from app.infrastructure.build.maven_runner import MavenNotAvailableError, MavenRewriteRunner
from app.infrastructure.migration_engine.internal_rewrite_runner import InternalRewriteRunner
from app.infrastructure.migration_engine.migration_log_parser import parse_rewrite_output
from app.infrastructure.migration_engine.recipe_mapper import RecipeMapper, _parse_major
from app.shared import file_utils

logger = logging.getLogger(__name__)

_BUILD_FILES = ("pom.xml", "build.gradle", "build.gradle.kts")


@dataclass
class MigrationRunResult:
    success: bool
    tool: str  # "maven" | "gradle" | "none"
    project_dir: Path | None = None
    recipes: list[str] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)
    error_lines: list[str] = field(default_factory=list)
    used_fallback: bool = False


class AutomatedMigrationRunner:
    def __init__(self) -> None:
        self._maven = MavenRewriteRunner()
        self._gradle = GradleRewriteRunner()
        self._fallback = InternalRewriteRunner()
        self._recipe_mapper = RecipeMapper()
        self._wrapper_upgrader = GradleWrapperUpgrader()

    def run(
        self,
        migrated_repo_dir: Path,
        build_tool: str,
        target_java_version: str | None,
        *,
        include_jakarta: bool,
    ) -> MigrationRunResult:
        project_dir = self._resolve_project_dir(migrated_repo_dir)
        plan = self._recipe_mapper.build_plan(target_java_version, include_jakarta=include_jakarta)

        # An old Gradle wrapper can't run on a newer target JDK (Java 21 needs
        # Gradle 8.5+), which breaks both rewriteRun and build validation. Bump it
        # first (text edit, no Gradle invocation) so those steps can launch.
        wrapper_lines: list[str] = []
        if build_tool == "GRADLE":
            wrapper_lines = self._wrapper_upgrader.ensure_compatible(
                project_dir, _parse_major(target_java_version)
            )
            for line in wrapper_lines:
                logger.info("%s", line)

        if not plan.has_recipes:
            return MigrationRunResult(
                success=True,
                tool="none",
                project_dir=project_dir,
                log_lines=wrapper_lines
                + ["No applicable OpenRewrite recipes for the selected target."],
            )

        logger.info(
            "OpenRewrite (%s) recipes=%s in %s",
            build_tool,
            plan.active_recipes_csv,
            project_dir.name,
        )

        if build_tool == "MAVEN":
            result = self._run_maven(project_dir, plan)
        elif build_tool == "GRADLE":
            result = self._run_gradle(project_dir, plan)
        else:
            result = MigrationRunResult(
                success=False,
                tool="none",
                error_lines=[f"Unsupported build tool: {build_tool}"],
            )
        result.recipes = plan.active_recipes
        result.project_dir = project_dir
        if wrapper_lines:
            result.log_lines = wrapper_lines + result.log_lines

        # If OpenRewrite failed, try the lightweight fallback so the published
        # repo at least targets the requested Java version.
        if not result.success:
            target_major = _parse_major(target_java_version)
            if target_major is not None:
                fallback_lines = self._fallback.bump_java_version(
                    project_dir, build_tool, target_major
                )
                if fallback_lines:
                    result.used_fallback = True
                    result.success = True
                    result.log_lines += fallback_lines
                    logger.info("Applied internal fallback: %s", "; ".join(fallback_lines))

        return result

    # -- runners ------------------------------------------------------------- #

    def _run_maven(self, project_dir: Path, plan) -> MigrationRunResult:
        try:
            command = self._maven.run(project_dir, plan)
        except MavenNotAvailableError as exc:
            return MigrationRunResult(success=False, tool="maven", error_lines=[str(exc)])
        parsed = parse_rewrite_output(command.stdout, command.stderr)
        return MigrationRunResult(
            success=command.succeeded,
            tool="maven",
            log_lines=parsed.lines,
            error_lines=parsed.error_lines,
        )

    def _run_gradle(self, project_dir: Path, plan) -> MigrationRunResult:
        if not self._gradle.is_available(project_dir):
            return MigrationRunResult(
                success=False,
                tool="gradle",
                error_lines=["Gradle (wrapper or system) was not found."],
            )
        command = self._gradle.run(project_dir, plan)
        parsed = parse_rewrite_output(command.stdout, command.stderr)
        return MigrationRunResult(
            success=command.succeeded,
            tool="gradle",
            log_lines=parsed.lines,
            error_lines=parsed.error_lines,
        )

    # -- helpers ------------------------------------------------------------- #

    @staticmethod
    def _resolve_project_dir(root: Path) -> Path:
        if any((root / name).is_file() for name in _BUILD_FILES):
            return root
        found = file_utils.find_shallowest_dir_with(root, _BUILD_FILES)
        return found or root
