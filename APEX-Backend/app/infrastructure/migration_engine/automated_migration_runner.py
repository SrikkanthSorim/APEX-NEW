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
from app.infrastructure.migration_engine.gradle_preflight_modernizer import GradlePreflightModernizer
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
from app.shared.command_runner import resolve_executable, run_command

logger = logging.getLogger(__name__)

_BUILD_FILES = ("pom.xml", "build.gradle", "build.gradle.kts")

_JAKARTA_MIN_TARGET = 17

SPRING_BOOT_CONVERSION_KEYS = {"spring_boot", "spring_to_spring_boot", "spring-boot"}
TEST_MIGRATION_KEYS = {"test_migration", "junit4_to_5", "junit4-to-5", "junit"}
DEPENDENCY_MIGRATION_KEYS = {"dependency_updates", "dependency_upgrade", "dependencies"}


@dataclass(frozen=True)
class MigrationPhase:
    id: str
    label: str
    optional: bool = True
    conversion_types: list[str] = field(default_factory=list)
    include_java_upgrade: bool = False
    include_conditional: bool = False
    include_spring_boot: bool = False
    include_dependency_currency: bool = False
    include_cleanup: bool = False
    cleanup_only: bool = False


@dataclass(frozen=True)
class GitCheckpoint:
    revision: str
    available: bool


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
    spring_conversion_requested: bool = False
    spring_conversion_supported: bool | None = None
    spring_conversion_note: str | None = None
    spring_boot_version_before: str | None = None
    spring_boot_version_after: str | None = None
    phase_results: list[dict] = field(default_factory=list)
    skipped_recipes: list[dict] = field(default_factory=list)


class AutomatedMigrationRunner:
    def __init__(self) -> None:
        self._maven = MavenRewriteRunner()
        self._gradle = GradleRewriteRunner()
        self._pom_sanitizer = PomSanitizer()
        self._gradle_preflight = GradlePreflightModernizer()
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
        target_major = _parse_major(effective_target_java_version)
        sanitizer_lines = self._pom_sanitizer.sanitize_project(project_dir) if build_tool == "MAVEN" else []
        gradle_preflight_lines = (
            self._gradle_preflight.modernize(project_dir, target_major)
            if build_tool == "GRADLE"
            else []
        )
        analysis = self._project_analyzer.analyze(project_dir)
        pre_dependency_versions = self._dependency_version_map(analysis)

        effective_conversion_types, jakarta_auto_reason = self._resolve_conversion_types(
            conversion_types or [],
            frameworks=analysis.frameworks,
            spring_boot_version=analysis.spring_boot_version,
            target_major=target_major,
        )
        effective_include_jakarta = include_jakarta or jakarta_auto_reason is not None

        spring_requested, spring_supported, spring_note = self._spring_conversion_status(
            effective_conversion_types, frameworks=analysis.frameworks,
        )
        spring_boot_version_before = analysis.spring_boot_version

        adjustment_lines = [target_adjustment] if target_adjustment else []
        preflight_lines = adjustment_lines + sanitizer_lines + gradle_preflight_lines
        reasons: list[str] = []
        if jakarta_auto_reason:
            reasons.append(jakarta_auto_reason)
            preflight_lines.append(jakarta_auto_reason)

        final_result = MigrationRunResult(
            success=True,
            tool="none",
            project_dir=project_dir,
            log_lines=list(preflight_lines),
            recipe_selection_reasons=list(reasons),
            build_modernization_lines=sanitizer_lines + gradle_preflight_lines,
            effective_target_java_version=effective_target_java_version,
            spring_conversion_requested=spring_requested,
            spring_conversion_supported=spring_supported,
            spring_conversion_note=spring_note,
            spring_boot_version_before=spring_boot_version_before,
        )

        any_recipe_ran = False
        phases = self._migration_phases(
            analysis,
            target_major=target_major,
            effective_conversion_types=effective_conversion_types,
            effective_include_jakarta=effective_include_jakarta,
            extra_recipes=extra_recipes,
        )

        for phase in phases:
            analysis = self._project_analyzer.analyze(project_dir)
            context = self._recipe_context(
                analysis,
                build_tool=build_tool,
                target_java_version=effective_target_java_version,
                conversion_types=phase.conversion_types,
            )
            phase_extra_recipes = extra_recipes if phase.id == "build-repair" else None
            plan = self._recipe_mapper.build_plan(
                effective_target_java_version,
                include_jakarta=effective_include_jakarta,
                context=context,
                extra_recipes=phase_extra_recipes,
                include_java_upgrade=phase.include_java_upgrade,
                include_conditional=phase.include_conditional,
                include_spring_boot=phase.include_spring_boot,
                include_dependency_currency=phase.include_dependency_currency,
                include_cleanup=phase.include_cleanup,
                cleanup_only=phase.cleanup_only,
            )
            phase_reasons = list(plan.selection_reasons)
            final_result.recipe_selection_reasons.extend(
                reason for reason in phase_reasons
                if reason not in final_result.recipe_selection_reasons
            )

            if not plan.has_recipes:
                final_result.phase_results.append({
                    "id": phase.id,
                    "label": phase.label,
                    "status": "skipped",
                    "reason": "No applicable recipes for this repository.",
                    "recipes": [],
                })
                continue

            logger.info(
                "OpenRewrite phase %s (%s) recipes=%s in %s",
                phase.id,
                build_tool,
                ", ".join(plan.active_recipes),
                project_dir.name,
            )
            final_result.log_lines.append(f"===== MIGRATION PHASE: {phase.label} =====")
            final_result.log_lines.extend(phase_reasons)

            checkpoint = self._checkpoint(project_dir) if phase.optional else None
            result = self._run_phase(project_dir, build_tool, plan, target_major)
            final_result.tool = result.tool

            if result.success:
                any_recipe_ran = True
                final_result.recipes.extend(
                    recipe for recipe in plan.active_recipes
                    if recipe not in final_result.recipes
                )
                final_result.log_lines.extend(result.log_lines)
                final_result.error_lines.extend(result.error_lines)
                final_result.phase_results.append({
                    "id": phase.id,
                    "label": phase.label,
                    "status": "completed",
                    "recipes": plan.active_recipes,
                })
                continue

            if phase.optional and self._restore_checkpoint(project_dir, checkpoint):
                reason = self._first_error(result)
                skipped = {
                    "phase": phase.id,
                    "label": phase.label,
                    "recipes": plan.active_recipes,
                    "reason": reason,
                }
                final_result.skipped_recipes.append(skipped)
                final_result.phase_results.append({
                    "id": phase.id,
                    "label": phase.label,
                    "status": "skipped",
                    "recipes": plan.active_recipes,
                    "reason": reason,
                })
                final_result.log_lines.extend(result.log_lines)
                final_result.log_lines.append(
                    f"Skipped optional phase '{phase.label}' because OpenRewrite failed: {reason}"
                )
                final_result.error_lines.extend(result.error_lines)
                continue

            result.recipes = plan.active_recipes
            result.project_dir = project_dir
            result.log_lines = final_result.log_lines + result.log_lines
            result.error_lines = final_result.error_lines + result.error_lines
            result.recipe_selection_reasons = final_result.recipe_selection_reasons
            result.build_modernization_lines = final_result.build_modernization_lines
            result.effective_target_java_version = effective_target_java_version
            result.spring_conversion_requested = spring_requested
            result.spring_conversion_supported = spring_supported
            result.spring_conversion_note = spring_note
            result.spring_boot_version_before = spring_boot_version_before
            result.phase_results = final_result.phase_results
            result.skipped_recipes = final_result.skipped_recipes
            return self._describe_failed_result(result, build_tool)

        if not any_recipe_ran:
            final_result.already_compatible = not sanitizer_lines
            final_result.log_lines.append(
                "Project is already compatible with the selected target Java "
                "version. No import or source code changes were required."
                if final_result.already_compatible
                else "No applicable OpenRewrite recipes for the selected target."
            )
        else:
            upgrades, final_result.spring_boot_version_after = self._diff_dependency_upgrades(
                project_dir, pre_dependency_versions
            )
            final_result.dependency_upgrades = [upgrade.to_dict() for upgrade in upgrades]

        return final_result

    def _describe_failed_result(
        self,
        result: MigrationRunResult,
        build_tool: str,
    ) -> MigrationRunResult:
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
        return result

    def _migration_phases(
        self,
        analysis: ProjectAnalysis,
        *,
        target_major: int | None,
        effective_conversion_types: list[str],
        effective_include_jakarta: bool,
        extra_recipes: list[ExtraRecipe] | None,
    ) -> list[MigrationPhase]:
        normalized = {
            str(item).strip().lower()
            for item in effective_conversion_types
            if str(item).strip()
        }
        source_major = _parse_major(analysis.current_java_version)
        phases: list[MigrationPhase] = []

        if target_major is not None and (source_major is None or source_major < target_major):
            phases.append(
                MigrationPhase(
                    id="java-version",
                    label="Java version migration",
                    optional=False,
                    conversion_types=["java_version"],
                    include_java_upgrade=True,
                )
            )

        if normalized & SPRING_BOOT_CONVERSION_KEYS:
            phases.append(
                MigrationPhase(
                    id="spring-boot",
                    label="Spring Boot migration",
                    conversion_types=["spring_boot"],
                    include_spring_boot=True,
                )
            )

        if effective_include_jakarta:
            phases.append(
                MigrationPhase(
                    id="jakarta",
                    label="Jakarta namespace migration",
                    conversion_types=["jakarta"],
                    include_conditional=True,
                )
            )

        if normalized & DEPENDENCY_MIGRATION_KEYS:
            phases.append(
                MigrationPhase(
                    id="dependencies",
                    label="Dependency currency updates",
                    conversion_types=["dependency_updates"],
                    include_dependency_currency=True,
                )
            )

        if extra_recipes:
            phases.append(
                MigrationPhase(
                    id="build-repair",
                    label="Build repair recipes",
                    optional=False,
                    conversion_types=list(effective_conversion_types),
                )
            )

        if normalized & TEST_MIGRATION_KEYS:
            phases.append(
                MigrationPhase(
                    id="test-migration",
                    label="Test framework migration",
                    conversion_types=["test_migration"],
                    include_conditional=True,
                )
            )

        if phases:
            phases.append(
                MigrationPhase(
                    id="cleanup",
                    label="Cleanup",
                    include_cleanup=True,
                    cleanup_only=True,
                )
            )
        return phases

    @staticmethod
    def _recipe_context(
        analysis: ProjectAnalysis,
        *,
        build_tool: str,
        target_java_version: str | None,
        conversion_types: list[str],
    ) -> MigrationRecipeContext:
        return MigrationRecipeContext(
            source_java_version=analysis.current_java_version,
            target_java_version=target_java_version,
            build_tool=build_tool,
            frameworks=analysis.frameworks,
            dependencies=[f"{dep.group_id}:{dep.artifact_id}" for dep in analysis.dependencies],
            build_plugins=[plugin.id for plugin in analysis.build_plugins],
            bom_versions=[f"{bom.group_id}:{bom.artifact_id}" for bom in analysis.bom_versions],
            conversion_types=conversion_types,
        )

    def _run_phase(
        self,
        project_dir: Path,
        build_tool: str,
        plan: RecipePlan,
        target_major: int | None,
    ) -> MigrationRunResult:
        if build_tool == "MAVEN":
            return self._run_maven(project_dir, plan, target_major)
        if build_tool == "GRADLE":
            return self._run_gradle(project_dir, plan, target_major)
        return MigrationRunResult(
            success=False,
            tool="none",
            error_lines=[f"Unsupported build tool: {build_tool}"],
        )

    @staticmethod
    def _first_error(result: MigrationRunResult) -> str:
        for line in result.error_lines:
            text = str(line).strip()
            if text:
                return text
        return "OpenRewrite phase failed. See logs for details."

    @staticmethod
    def _checkpoint(project_dir: Path) -> GitCheckpoint | None:
        git = resolve_executable("git")
        if not git:
            return GitCheckpoint(revision="", available=False)

        commands = (
            ["init", "-q"],
            ["config", "user.name", "JavaApex Migration"],
            ["config", "user.email", "migration@javaapex.local"],
            ["add", "-A"],
            ["commit", "--allow-empty", "-q", "-m", "javaapex migration checkpoint"],
        )
        for args in commands:
            result = run_command([git, *args], cwd=project_dir, timeout=60)
            if not result.succeeded:
                logger.warning("Unable to create migration checkpoint: git %s failed", args[0])
                return GitCheckpoint(revision="", available=False)

        head = run_command([git, "rev-parse", "HEAD"], cwd=project_dir, timeout=30)
        if not head.succeeded:
            return GitCheckpoint(revision="", available=False)
        return GitCheckpoint(revision=head.stdout.strip(), available=True)

    @staticmethod
    def _restore_checkpoint(project_dir: Path, checkpoint: GitCheckpoint | None) -> bool:
        if checkpoint is None:
            return False
        if not checkpoint.available or not checkpoint.revision:
            return False
        git = resolve_executable("git")
        if not git:
            return False
        reset = run_command(
            [git, "reset", "--hard", checkpoint.revision],
            cwd=project_dir,
            timeout=60,
        )
        clean = run_command([git, "clean", "-fd"], cwd=project_dir, timeout=60)
        if not reset.succeeded or not clean.succeeded:
            logger.warning("Unable to restore migration checkpoint.")
            return False
        return True

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
    ) -> tuple[list[DependencyUpgrade], str | None]:
        """Observe what OpenRewrite actually changed by re-reading the build
        file after the run, rather than predicting it beforehand -- dependency
        version numbers are resolved by OpenRewrite itself (``latest.release``
        / ``latest.patch``), never by this codebase. Also surfaces the
        post-migration Spring Boot version off the same re-analysis, so a
        second ``ProjectAnalyzer.analyze`` call isn't needed just for that.
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
        return upgrades, post_analysis.spring_boot_version

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

    @staticmethod
    def _spring_conversion_status(
        requested: list[str], *, frameworks: list[str],
    ) -> tuple[bool, bool | None, str | None]:
        """Attribute the "Spring -> Spring Boot" conversion type against what
        was actually detected. Scoped to Boot-to-Boot upgrades only -- the
        upgrade ladder in the recipe catalog already runs unconditionally for
        any detected Spring Boot project regardless of this conversion type,
        so this method never changes recipe selection; it only decides
        whether that (unconditional) behavior should be attributed to an
        explicit user request, or reported as not supported for a legacy
        (non-Boot) Spring Framework project, where OpenRewrite has no
        automated bootstrapping recipe upstream.
        """
        normalized = {str(item).strip().lower() for item in requested}
        if not (normalized & SPRING_BOOT_CONVERSION_KEYS):
            return False, None, None

        framework_set = {item.lower() for item in frameworks}
        if "spring-boot" in framework_set:
            return True, True, (
                "Detected an existing Spring Boot application; applying "
                "OpenRewrite's Spring Boot upgrade ladder toward a version "
                "compatible with the selected target Java version."
            )
        if "spring-framework" in framework_set:
            return True, False, (
                "Legacy Spring Framework (non-Boot) to Spring Boot conversion "
                "is not yet supported: OpenRewrite has no automated recipe "
                "for bootstrapping a plain Spring Framework project into "
                "Spring Boot (removing web.xml, converting XML bean "
                "configuration, adding an embedded server, etc.). No changes "
                "were applied for this conversion type."
            )
        return True, False, (
            "No Spring Framework or Spring Boot dependency was detected in "
            "this project; the Spring -> Spring Boot conversion type does "
            "not apply."
        )
