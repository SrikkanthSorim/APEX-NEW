"""Orchestrates the actual code migration on the migrated-repo.

Resolves the project directory, builds the (declarative, dynamically
parameterized) OpenRewrite recipe plan, and dispatches to the Maven or Gradle
runner. If the build tool itself isn't available in this environment, that
limitation is reported plainly rather than papered over with a hand-written
fallback -- every actual content change comes from an OpenRewrite recipe.
Never touches original-repo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.infrastructure.build.gradle_runner import GradleRewriteRunner
from app.infrastructure.build.maven_runner import MavenNotAvailableError, MavenRewriteRunner
from app.infrastructure.analyzers.project_analyzer import ProjectAnalysis, ProjectAnalyzer
from app.infrastructure.java_runtime import build_compatible_java_target
from app.infrastructure.migration_engine.migration_log_parser import parse_rewrite_output
from app.infrastructure.migration_engine.pom_sanitizer import PomSanitizer
from app.infrastructure.migration_engine.recipe_mapper import (
    ExtraRecipe,
    MigrationRecipeContext,
    RecipeMapper,
    RecipePlan,
    _parse_major,
)
from app.shared import file_utils

logger = logging.getLogger(__name__)

_BUILD_FILES = ("pom.xml", "build.gradle", "build.gradle.kts")

_JAKARTA_MIN_TARGET = 17


@dataclass(frozen=True)
class DependencyUpgrade:
    coordinate: str
    old_version: str | None
    new_version: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "coordinate": self.coordinate,
            "oldVersion": self.old_version,
            "newVersion": self.new_version,
        }


@dataclass
class MigrationRunResult:
    success: bool
    tool: str  # "maven" | "gradle" | "none"
    project_dir: Path | None = None
    recipes: list[str] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)
    error_lines: list[str] = field(default_factory=list)
    used_fallback: bool = False
    tool_unavailable: bool = False
    # True when the build tool failed while evaluating/compiling the project
    # itself, before any OpenRewrite recipe ran -- a project-level build
    # configuration/plugin incompatibility, not something recipe selection
    # could have prevented or fixed.
    pre_recipe_failure: bool = False
    recipe_selection_reasons: list[str] = field(default_factory=list)
    build_modernization_lines: list[str] = field(default_factory=list)
    dependency_upgrades: list[dict] = field(default_factory=list)
    effective_target_java_version: str | None = None
    already_compatible: bool = False


class AutomatedMigrationRunner:
    def __init__(self) -> None:
        self._maven = MavenRewriteRunner()
        self._gradle = GradleRewriteRunner()
        self._pom_sanitizer = PomSanitizer()
        self._project_analyzer = ProjectAnalyzer()
        self._recipe_mapper = RecipeMapper()

    def run(
        self,
        migrated_repo_dir: Path,
        build_tool: str,
        target_java_version: str | None,
        *,
        include_jakarta: bool,
        conversion_types: list[str] | None = None,
        extra_recipes: list[ExtraRecipe] | None = None,
    ) -> MigrationRunResult:
        project_dir = self._resolve_project_dir(migrated_repo_dir)
        effective_target_java_version, target_adjustment = build_compatible_java_target(
            target_java_version
        )
        sanitizer_lines = self._pom_sanitizer.sanitize_project(project_dir) if build_tool == "MAVEN" else []
        analysis = self._project_analyzer.analyze(project_dir)
        pre_dependency_versions = self._dependency_version_map(analysis)

        effective_conversion_types, jakarta_auto_reason = self._resolve_conversion_types(
            conversion_types or [],
            frameworks=analysis.frameworks,
            spring_boot_version=analysis.spring_boot_version,
            target_major=_parse_major(effective_target_java_version),
        )
        effective_include_jakarta = include_jakarta or jakarta_auto_reason is not None

        context = MigrationRecipeContext(
            source_java_version=analysis.current_java_version,
            target_java_version=effective_target_java_version,
            build_tool=build_tool,
            frameworks=analysis.frameworks,
            dependencies=[f"{dep.group_id}:{dep.artifact_id}" for dep in analysis.dependencies],
            build_plugins=[plugin.id for plugin in analysis.build_plugins],
            bom_versions=[f"{bom.group_id}:{bom.artifact_id}" for bom in analysis.bom_versions],
            conversion_types=effective_conversion_types,
        )
        plan = self._recipe_mapper.build_plan(
            effective_target_java_version,
            include_jakarta=effective_include_jakarta,
            context=context,
            extra_recipes=extra_recipes,
        )
        adjustment_lines = [target_adjustment] if target_adjustment else []
        reasons = list(plan.selection_reasons)
        if jakarta_auto_reason:
            reasons.append(jakarta_auto_reason)
        preflight_lines = adjustment_lines + sanitizer_lines + reasons

        if not plan.has_recipes:
            already_compatible = not sanitizer_lines
            completion_message = (
                "Project is already compatible with the selected target Java "
                "version. No import or source code changes were required."
                if already_compatible
                else "No applicable OpenRewrite recipes for the selected target."
            )
            return MigrationRunResult(
                success=True,
                tool="none",
                project_dir=project_dir,
                log_lines=preflight_lines + [completion_message],
                recipe_selection_reasons=reasons,
                effective_target_java_version=effective_target_java_version,
                already_compatible=already_compatible,
            )

        logger.info(
            "OpenRewrite (%s) recipes=%s in %s",
            build_tool,
            ", ".join(plan.active_recipes),
            project_dir.name,
        )

        target_major = _parse_major(effective_target_java_version)
        if build_tool == "MAVEN":
            result = self._run_maven(project_dir, plan, target_major)
        elif build_tool == "GRADLE":
            result = self._run_gradle(project_dir, plan, target_major)
        else:
            result = MigrationRunResult(
                success=False,
                tool="none",
                error_lines=[f"Unsupported build tool: {build_tool}"],
            )
        result.recipes = plan.active_recipes
        result.project_dir = project_dir
        result.log_lines = preflight_lines + result.log_lines
        result.recipe_selection_reasons = reasons
        result.effective_target_java_version = effective_target_java_version

        if not result.success and result.tool_unavailable:
            # A genuine environment limitation (the build tool itself isn't
            # installed) -- report it plainly, same spirit as how
            # BuildValidator reports "no matching local JDK" as an
            # environment limitation rather than a migration failure. No
            # source or build-file changes are fabricated here.
            result.log_lines.append(
                f"OpenRewrite could not run: {build_tool.title()} tooling was "
                "not found in this environment. No source or build "
                "configuration changes were made; install/configure "
                f"{build_tool.title()} to complete this migration."
            )
        elif not result.success and result.pre_recipe_failure:
            # The build failed while evaluating/compiling the project itself
            # (see the build error above), before OpenRewrite's own recipe
            # task ever ran. No recipe selection could have prevented this --
            # it is a project-level build configuration or plugin
            # incompatibility (e.g. a dependency/plugin that cannot resolve
            # or load under the build tool version used here) that needs a
            # manual fix in the source repository.
            result.log_lines.append(
                f"{build_tool.title()} failed while evaluating/compiling the "
                "project itself -- before any OpenRewrite recipe ran. This is "
                "a project-level build configuration or plugin incompatibility "
                "(see the build error above), not something a migration "
                "recipe can fix automatically; it typically requires a manual "
                "fix in the source repository (e.g. removing or upgrading an "
                "incompatible plugin/dependency) before automated migration "
                "can proceed."
            )
        elif result.success and plan.has_recipes:
            result.dependency_upgrades = [
                upgrade.to_dict()
                for upgrade in self._diff_dependency_upgrades(project_dir, pre_dependency_versions)
            ]

        return result

    # -- runners ------------------------------------------------------------- #

    def _run_maven(self, project_dir: Path, plan: RecipePlan, target_major: int | None = None) -> MigrationRunResult:
        try:
            command = self._maven.run(project_dir, plan, target_major)
        except MavenNotAvailableError as exc:
            return MigrationRunResult(success=False, tool="maven", tool_unavailable=True, error_lines=[str(exc)])
        parsed = parse_rewrite_output(command.stdout, command.stderr)
        return MigrationRunResult(
            success=command.succeeded,
            tool="maven",
            log_lines=parsed.lines,
            error_lines=parsed.error_lines,
            pre_recipe_failure=not command.succeeded and not parsed.reached_recipe_execution,
        )

    def _run_gradle(self, project_dir: Path, plan: RecipePlan, target_major: int | None = None) -> MigrationRunResult:
        if not self._gradle.is_available(project_dir):
            return MigrationRunResult(
                success=False,
                tool="gradle",
                tool_unavailable=True,
                error_lines=["Gradle (wrapper or system) was not found."],
            )
        command = self._gradle.run(project_dir, plan, target_major)
        parsed = parse_rewrite_output(command.stdout, command.stderr)
        return MigrationRunResult(
            success=command.succeeded,
            tool="gradle",
            log_lines=parsed.lines,
            error_lines=parsed.error_lines,
            pre_recipe_failure=not command.succeeded and not parsed.reached_recipe_execution,
        )

    # -- helpers ------------------------------------------------------------- #

    @staticmethod
    def _resolve_project_dir(root: Path) -> Path:
        if any((root / name).is_file() for name in _BUILD_FILES):
            return root
        found = file_utils.find_shallowest_dir_with(root, _BUILD_FILES)
        return found or root

    @staticmethod
    def _dependency_version_map(analysis: ProjectAnalysis) -> dict[str, str | None]:
        return {f"{dep.group_id}:{dep.artifact_id}": dep.version for dep in analysis.dependencies}

    def _diff_dependency_upgrades(
        self, project_dir: Path, pre_versions: dict[str, str | None]
    ) -> list[DependencyUpgrade]:
        """Observe what OpenRewrite actually changed by re-reading the build
        file after the run, rather than predicting it beforehand -- dependency
        version numbers are resolved by OpenRewrite itself (``latest.release``
        / ``latest.patch``), never by this codebase.
        """
        post_analysis = self._project_analyzer.analyze(project_dir)
        upgrades: list[DependencyUpgrade] = []
        for dep in post_analysis.dependencies:
            key = f"{dep.group_id}:{dep.artifact_id}"
            if key not in pre_versions:
                continue
            old_version = pre_versions[key]
            if dep.version and dep.version != old_version:
                upgrades.append(DependencyUpgrade(key, old_version, dep.version))
        return upgrades

    @staticmethod
    def _resolve_conversion_types(
        requested: list[str],
        *,
        frameworks: list[str],
        spring_boot_version: str | None,
        target_major: int | None,
    ) -> tuple[list[str], str | None]:
        """Union the user-requested conversions with auto-detected ones.

        Automatically requires the javax.* -> jakarta.* migration once the
        target Java version is 17+ (the Jakarta EE 9 rename threshold most
        tooling aligns with) and the project shows a concrete signal that it
        still depends on the javax.* namespace: either a direct javax EE
        library dependency, or a Spring Boot version below 3.x (Spring Boot 3
        requires Jakarta EE). Explicit user selection is preserved as-is; this
        only adds to it, never removes a user's choice.
        """
        resolved = list(requested)
        normalized = {str(item).strip().lower() for item in resolved}
        if target_major is None or target_major < _JAKARTA_MIN_TARGET:
            return resolved, None

        already_jakarta = "jakarta-ee" in frameworks and "javax-ee" not in frameworks
        if already_jakarta:
            return resolved, None

        spring_boot_major = None
        if spring_boot_version:
            try:
                spring_boot_major = int(str(spring_boot_version).split(".", 1)[0])
            except ValueError:
                spring_boot_major = None

        trigger: str | None = None
        if "javax-ee" in frameworks:
            trigger = "javax EE library dependency detected"
        elif "spring-boot" in frameworks and (spring_boot_major is None or spring_boot_major < 3):
            trigger = f"Spring Boot {spring_boot_version or 'legacy'} depends on javax.*"

        if trigger and "jakarta" not in normalized:
            resolved.append("jakarta")
            return resolved, (
                f"Auto-detected javax.* -> jakarta.* migration requirement for "
                f"target Java {target_major} ({trigger})"
            )
        return resolved, None
