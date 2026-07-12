"""Start Migration use case.

Runs OpenRewrite on a copy of the cloned repo,
then publishes the result to the configured destination (a new repo under
Javaapex by default). Long-running; driven in a background thread by the
pipeline. All state is persisted to ``migration-report.json`` for polling.
original-repo is never modified.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.application.services import progress_service
from app.application.services.status_service import MigrationReportStore
from app.core.config import settings
from app.core.exceptions import (
    DiscoveryReportRequiredError,
    MigrationExecutionError,
    MigrationJobNotFoundError,
)
from app.domain.enums.migration_status import MigrationStatus, MigrationStep
from app.domain.models.build_result import BuildResult
from app.infrastructure.build.build_validator import BuildValidator
from app.infrastructure.github.branch_creator import BranchCreator
from app.infrastructure.github.repo_creator import RepoCreator
from app.infrastructure.github.repo_pusher import RepoPusher
from app.infrastructure.migration_engine import build_failure_diagnostician
from app.infrastructure.migration_engine.automated_migration_runner import (
    AutomatedMigrationRunner,
    MigrationRunResult,
)
from app.infrastructure.migration_engine.change_analyzer import ChangeAnalysis, ChangeAnalyzer
from app.infrastructure.migration_engine.gradle_buildscript_repair import GradleBuildscriptRepair
from app.infrastructure.migration_engine.recipe_mapper import ExtraRecipe, load_catalog, recipe_entry_name
from app.infrastructure.persistence.job_repository import JobRepository
from app.infrastructure.quality_gates.quality_gate_runner import QualityGateRunner
from app.infrastructure.workspace.workspace_manager import WorkspaceManager
from app.infrastructure.workspace.workspace_paths import WorkspacePaths

logger = logging.getLogger(__name__)

MODE_CREATE_NEW_REPO = "CREATE_NEW_REPO"
MODE_EXISTING_REPO_BRANCH = "EXISTING_REPO_BRANCH"
MODE_LOCAL_FOLDER = "LOCAL_FOLDER"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StartMigrationUseCase:
    def __init__(
        self,
        job_repository: JobRepository | None = None,
        runner: AutomatedMigrationRunner | None = None,
        repo_creator: RepoCreator | None = None,
        repo_pusher: RepoPusher | None = None,
        branch_creator: BranchCreator | None = None,
        build_validator: BuildValidator | None = None,
        quality_gate_runner: QualityGateRunner | None = None,
        change_analyzer: ChangeAnalyzer | None = None,
        gradle_buildscript_repair: GradleBuildscriptRepair | None = None,
    ) -> None:
        self._job_repository = job_repository or JobRepository()
        self._runner = runner or AutomatedMigrationRunner()
        self._repo_creator = repo_creator or RepoCreator()
        self._repo_pusher = repo_pusher or RepoPusher()
        self._branch_creator = branch_creator or BranchCreator()
        self._build_validator = build_validator or BuildValidator()
        self._quality_gate_runner = quality_gate_runner or QualityGateRunner()
        self._change_analyzer = change_analyzer or ChangeAnalyzer()
        self._gradle_buildscript_repair = gradle_buildscript_repair or GradleBuildscriptRepair()

    # ------------------------------------------------------------------ #
    # Phase 1: validate + write the initial queued report (synchronous)
    # ------------------------------------------------------------------ #
    def prepare(self, job_id: str, request: dict[str, Any] | None) -> dict[str, Any]:
        if not self._job_repository.job_exists(job_id):
            raise MigrationJobNotFoundError()

        connect = self._job_repository.read_connect_report(job_id)
        discovery = self._job_repository.read_discovery_report(job_id)
        if not connect or not discovery:
            raise DiscoveryReportRequiredError()

        config = self._job_repository.read_migration_config_report(job_id) or {}
        request = request or {}
        options = config.get("options") or {}

        source_repo_url = connect.get("repoUrl") or discovery.get("repoUrl") or ""
        build_tool = (discovery.get("buildTool") or "").upper()
        source_java = (
            config.get("sourceJavaVersion")
            or request.get("source_java_version")
            or discovery.get("currentJavaVersion")
            or ""
        )
        target_java = (
            config.get("targetJavaVersion") or request.get("target_java_version") or ""
        )
        if not target_java:
            raise MigrationExecutionError("No target Java version selected.")

        destination = self._resolve_destination(config, connect)

        store = MigrationReportStore(WorkspacePaths(job_id))
        report = {
            "jobId": job_id,
            "status": MigrationStatus.QUEUED.value,
            "currentStep": MigrationStep.QUEUED.value,
            "progressPercent": 0,
            "sourceRepoUrl": source_repo_url,
            "sourceJavaVersion": str(source_java),
            "targetJavaVersion": str(target_java),
            "buildTool": build_tool,
            "conversionTypes": config.get("conversionTypes")
            or request.get("conversion_types")
            or [],
            "options": options,
            "runSonar": bool(options.get("runSonar") or request.get("run_sonar")),
            "runFossa": bool(options.get("runFossa") or request.get("run_fossa")),
            "runTests": bool(options.get("runTests") or request.get("run_tests")),
            "destination": destination,
            "targetRepo": None,
            "startedAt": _now(),
            "completedAt": None,
            "errorMessage": None,
            "filesModified": 0,
            "recipes": [],
            "usedFallback": False,
            "logLines": [],
        }
        store.write(report)
        logger.info("Migration queued for job %s (target Java %s)", job_id, target_java)
        return report

    # ------------------------------------------------------------------ #
    # Phase 2: the long-running job (runs in a background thread)
    # ------------------------------------------------------------------ #
    def run(self, job_id: str) -> None:
        paths = WorkspacePaths(job_id)
        store = MigrationReportStore(paths)
        report = store.read() or {}
        build_tool = report.get("buildTool", "")
        target_java = report.get("targetJavaVersion", "")
        conversion_types = report.get("conversionTypes") or []

        try:
            # --- Prepare migrated-repo ---
            progress_service.set_phase(
                store, status=MigrationStatus.RUNNING.value,
                step=MigrationStep.PREPARING.value, percent=10,
            )
            WorkspaceManager(paths).prepare_migrated_repo()

            # --- Run OpenRewrite (selected migration recipes), diagnosing and
            #     retrying with additional recipes if the build fails ---
            progress_service.set_phase(
                store, status=MigrationStatus.RUNNING.value,
                step=MigrationStep.MIGRATING.value, percent=35,
            )
            result, build_result, retry_attempts = self._run_migration_with_retries(
                store, job_id, paths, build_tool, target_java, report, conversion_types,
            )
            store.update(
                recipes=result.recipes,
                usedFallback=result.used_fallback,
                effectiveTargetJavaVersion=result.effective_target_java_version,
                recipeSelection=result.recipe_selection_reasons,
                buildModernization=result.build_modernization_lines,
                dependencyUpgrades=result.dependency_upgrades,
                alreadyCompatible=result.already_compatible,
                retryAttempts=retry_attempts,
            )

            if not result.success:
                self._fail(store, job_id, self._describe_migration_failure(result))
                return

            change_analysis = self._change_analyzer.analyze(
                paths.original_repo_dir, paths.migrated_repo_dir
            )
            files_modified = change_analysis.files_modified_count
            store.update(
                filesModified=files_modified,
                modifiedFiles=change_analysis.all_changed_files[:200],
                importChanges=[change.to_dict() for change in change_analysis.import_changes[:200]],
                sourceChanges=[change.to_dict() for change in change_analysis.source_changes[:200]],
                progressPercent=60,
            )
            if not change_analysis.import_changes and not change_analysis.source_changes:
                store.append_logs(
                    ["No import or source code changes were required for this migration."]
                )
            logger.info("Migration changed %d file(s) for job %s", files_modified, job_id)

            # --- Record the (already-obtained) build validation outcome ---
            progress_service.set_phase(
                store, status=MigrationStatus.RUNNING.value,
                step=MigrationStep.VALIDATING.value, percent=70,
            )
            self._record_build_result(store, job_id, build_result)
            store.update(
                migrationSummary=self._build_migration_summary(
                    store.read() or {}, result, change_analysis, retry_attempts
                )
            )

            # --- Optional Quality Gates (SonarQube/FOSSA) ---
            self._run_quality_gates(store, job_id, result.project_dir, report)

            # --- Publish ---
            progress_service.set_phase(
                store, status=MigrationStatus.RUNNING.value,
                step=MigrationStep.PUBLISHING.value, percent=85,
            )
            publish_target_java = result.effective_target_java_version or target_java
            target_repo = self._publish(store, report, paths, publish_target_java)

            # --- Done ---
            store.update(
                status=MigrationStatus.COMPLETED.value,
                currentStep=MigrationStep.COMPLETED.value,
                progressPercent=100,
                targetRepo=target_repo,
                completedAt=_now(),
            )
            store.append_logs([f"Migration completed. Published to {target_repo}"])
            logger.info("Migration completed for job %s -> %s", job_id, target_repo)

        except MigrationExecutionError as exc:
            self._fail(store, job_id, exc.message)
        except Exception as exc:  # noqa: BLE001 - report any unexpected failure cleanly
            logger.exception("Unexpected migration failure for job %s", job_id)
            self._fail(store, job_id, "Migration failed due to an unexpected error.")

    # -- migration run + diagnose-and-retry loop ------------------------------ #

    def _run_migration_with_retries(
        self,
        store: MigrationReportStore,
        job_id: str,
        paths: WorkspacePaths,
        build_tool: str,
        target_java: str,
        report: dict[str, Any],
        conversion_types: list[str],
    ) -> tuple[MigrationRunResult, BuildResult | None, list[dict[str, Any]]]:
        """Run OpenRewrite, validate the build, and -- if it fails -- diagnose
        the root cause and retry with additional OpenRewrite recipes, or (for
        a Gradle project that crashed before OpenRewrite could even run) a
        same-coordinate buildscript version repair.

        Bounded by ``settings.migration_max_retry_attempts``. Every attempt
        beyond the first only adds recipes the diagnostician (data-driven from
        the recipe catalog's ``errorSignalRecipes``) could actually justify
        from the build's own error output; it stops as soon as the build
        succeeds, retries are exhausted, or no new recipe can be identified.
        """
        include_jakarta = self._should_include_jakarta(report)
        max_attempts = max(0, settings.migration_max_retry_attempts)
        extra_recipes: list[ExtraRecipe] = []
        retry_attempts: list[dict[str, Any]] = []
        result: MigrationRunResult | None = None
        build_result: BuildResult | None = None
        catalog = load_catalog()
        # Each attempt's MigrationRunResult only reflects what changed *in
        # that attempt* (recipe_mapper re-analyzes the already-modified repo
        # each time); accumulate across attempts so the final report/summary
        # reflects everything OpenRewrite did over the whole retry loop.
        cumulative_recipes: list[str] = []
        cumulative_dependency_upgrades: list[dict] = []

        for attempt in range(max_attempts + 1):
            result = self._runner.run(
                paths.migrated_repo_dir,
                build_tool,
                target_java,
                include_jakarta=include_jakarta,
                conversion_types=conversion_types,
                extra_recipes=extra_recipes or None,
            )
            store.append_logs(result.log_lines + result.error_lines)
            for recipe in result.recipes:
                if recipe not in cumulative_recipes:
                    cumulative_recipes.append(recipe)
            cumulative_dependency_upgrades.extend(result.dependency_upgrades)
            result.recipes = cumulative_recipes
            result.dependency_upgrades = cumulative_dependency_upgrades

            if not result.success:
                if (
                    result.pre_recipe_failure
                    and not result.tool_unavailable
                    and build_tool == "GRADLE"
                    and result.project_dir is not None
                    and attempt < max_attempts
                ):
                    # Gradle crashed evaluating the project itself, before
                    # OpenRewrite could run -- try a same-coordinate,
                    # dynamically-resolved classpath/plugin version repair
                    # (see GradleBuildscriptRepair) and, if one was found and
                    # applied, retry from scratch.
                    repair_lines, repair = self._gradle_buildscript_repair.repair(
                        result.project_dir, "\n".join(result.log_lines + result.error_lines)
                    )
                    if repair is not None:
                        store.append_logs(repair_lines)
                        retry_attempts.append({
                            "attempt": attempt + 1,
                            "rootCause": (
                                "Gradle failed evaluating the project before OpenRewrite "
                                f"could run (implicated: {repair.coordinate} {repair.old_version})."
                            ),
                            "recipesAdded": [
                                f"buildscript-repair: {repair.coordinate} "
                                f"{repair.old_version} -> {repair.new_version}"
                            ],
                            "buildStatus": "PRE-RECIPE FAILURE",
                        })
                        continue
                # Nothing more to try: tool unavailable, no same-coordinate
                # repair could be identified/applied, or retries exhausted.
                break

            build_result = self._run_build_validation(job_id, result, build_tool)
            if build_result is None or build_result.skipped or build_result.success:
                break
            if attempt >= max_attempts:
                break

            diagnoses = build_failure_diagnostician.diagnose(build_result.error_lines, catalog)
            new_recipes: list[ExtraRecipe] = [
                (diagnosis.recipe_entry, diagnosis.artifact_key, diagnosis.reason)
                for diagnosis in diagnoses
                if (diagnosis.recipe_entry, diagnosis.artifact_key, diagnosis.reason) not in extra_recipes
            ]
            if not new_recipes:
                store.append_logs(
                    ["Build failed and no additional OpenRewrite recipe could be "
                     "identified automatically from the build output."]
                )
                break

            root_cause = "; ".join(diagnosis.reason for diagnosis in diagnoses)
            recipes_added = [recipe_entry_name(entry) for entry, _artifact, _reason in new_recipes]
            store.append_logs([
                f"Build failed (attempt {attempt + 1}). Root cause analysis: {root_cause}",
                f"Retrying with additional OpenRewrite recipe(s): {', '.join(recipes_added)}",
            ])
            retry_attempts.append({
                "attempt": attempt + 1,
                "rootCause": root_cause,
                "recipesAdded": recipes_added,
                "buildStatus": build_result.status_label,
            })
            extra_recipes.extend(new_recipes)

        assert result is not None  # loop always runs at least once
        return result, build_result, retry_attempts

    # -- build validation ---------------------------------------------------- #

    def _run_build_validation(
        self, job_id: str, result: MigrationRunResult, build_tool: str,
    ) -> BuildResult | None:
        """Compile/package the migrated code (no report/log side effects)."""
        if result.project_dir is None:
            return None
        target_major = None
        if result.effective_target_java_version:
            try:
                target_major = int(str(result.effective_target_java_version).strip())
            except ValueError:
                target_major = None
        logger.info("Validating build for job %s (%s) ...", job_id, build_tool)
        return self._build_validator.validate(result.project_dir, build_tool, target_major)

    def _record_build_result(
        self, store: MigrationReportStore, job_id: str, result: BuildResult | None,
    ) -> None:
        """Persist a (already-obtained) build validation outcome to the report.

        Non-blocking: a failed build is reported (logs + report) but the
        migrated repo is still published so it can be inspected.
        """
        if result is None:
            return
        store.update(buildStatus=result.status_label, buildSuccess=result.success)
        store.append_logs(
            [f"===== {result.status_label} ({result.tool}) ====="]
            + result.error_lines[:20]
            + result.log_lines[-15:]
        )
        if result.skipped:
            logger.info("Build validation skipped for job %s", job_id)
        elif result.success:
            logger.info("BUILD SUCCESS for job %s (migrated repo compiles)", job_id)
        else:
            logger.warning("BUILD FAILED for job %s (migrated repo did not build)", job_id)

    # -- migration report summary --------------------------------------------- #

    @staticmethod
    def _build_migration_summary(
        report: dict[str, Any],
        result: MigrationRunResult,
        change_analysis: ChangeAnalysis,
        retry_attempts: list[dict[str, Any]] | None = None,
    ) -> str:
        """Plain-language rollup of what the migration did, for the report."""
        source = report.get("sourceJavaVersion") or "unknown"
        target = result.effective_target_java_version or report.get("targetJavaVersion") or "unknown"
        parts = [f"Migrated project from Java {source} to Java {target}."]

        if retry_attempts:
            causes = "; ".join(attempt["rootCause"] for attempt in retry_attempts)
            parts.append(
                f"The build failed after the first pass and was automatically "
                f"retried {len(retry_attempts)} time(s) with additional "
                f"OpenRewrite recipes based on root-cause analysis of the build "
                f"output ({causes})."
            )

        if result.already_compatible:
            parts.append(
                "Project was already compatible with the selected target Java "
                "version; no import or source code changes were required."
            )
        elif result.recipes:
            parts.append(
                f"Executed {len(result.recipes)} OpenRewrite recipe(s): {', '.join(result.recipes)}."
            )
        elif result.used_fallback:
            parts.append(
                "Applied deterministic build-configuration fallback (OpenRewrite did not run)."
            )

        if result.dependency_upgrades:
            upgrades = ", ".join(
                f"{upgrade['coordinate']} {upgrade.get('oldVersion') or '?'} -> {upgrade['newVersion']}"
                for upgrade in result.dependency_upgrades
            )
            parts.append(
                f"Upgraded {len(result.dependency_upgrades)} dependency/dependencies: {upgrades}."
            )

        if change_analysis.import_changes:
            parts.append(f"Updated imports in {len(change_analysis.import_changes)} file(s).")
        if change_analysis.source_changes:
            parts.append(f"Modified source code in {len(change_analysis.source_changes)} file(s).")

        build_status = report.get("buildStatus")
        if build_status:
            parts.append(f"Build validation result: {build_status}.")

        return " ".join(parts)

    # -- optional quality gates --------------------------------------------- #

    def _run_quality_gates(
        self,
        store: MigrationReportStore,
        job_id: str,
        project_dir: Any,
        report: dict[str, Any],
    ) -> None:
        if project_dir is None:
            return

        run_sonar = bool(report.get("runSonar"))
        run_fossa = bool(report.get("runFossa"))
        if not run_sonar and not run_fossa:
            return

        progress_service.set_phase(
            store,
            status=MigrationStatus.RUNNING.value,
            step=MigrationStep.QUALITY_GATES.value,
            percent=78,
        )
        store.append_logs(["===== QUALITY GATES ====="])

        project_name = str(report.get("targetRepo") or report.get("sourceRepoUrl") or job_id)
        result = self._quality_gate_runner.run(
            project_dir,
            job_id=job_id,
            project_name=project_name,
            run_sonar=run_sonar,
            run_fossa=run_fossa,
        )

        updates: dict[str, Any] = {}
        if result.sonar:
            updates.update(
                sonar_quality_gate=result.sonar.quality_gate,
                sonar_bugs=result.sonar.bugs,
                sonar_vulnerabilities=result.sonar.vulnerabilities,
                sonar_code_smells=result.sonar.code_smells,
                sonar_coverage=result.sonar.coverage,
                sonar_duplications=result.sonar.duplications,
                sonar_security_hotspots=result.sonar.security_hotspots,
                sonar_scan_mode=result.sonar.scan_mode,
                sonar_real_scan=result.sonar.real_scan,
                sonar_analysis_url=result.sonar.analysis_url,
                sonar_error_message=result.sonar.error_message,
                sonar_report=result.sonar.report,
            )
        if result.fossa:
            updates.update(
                fossa_policy_status=result.fossa.policy_status,
                fossa_total_dependencies=result.fossa.total_dependencies,
                fossa_license_issues=result.fossa.license_issues,
                fossa_vulnerabilities=result.fossa.vulnerabilities,
                fossa_outdated_dependencies=result.fossa.outdated_dependencies,
                fossa_scan_mode=result.fossa.scan_mode,
                fossa_real_scan=result.fossa.real_scan,
                fossa_analysis_url=result.fossa.analysis_url,
                fossa_error_message=result.fossa.error_message,
                fossa_report=result.fossa.report,
            )

        if updates:
            store.update(**updates)
        store.append_logs(result.log_lines)

    @staticmethod
    def _should_include_jakarta(report: dict[str, Any]) -> bool:
        conversions = {
            str(item).strip().lower()
            for item in (report.get("conversionTypes") or [])
            if str(item).strip()
        }
        return bool(
            conversions
            & {
                "jakarta",
                "javax_to_jakarta",
                "javax-jakarta",
                "javax_to_jakarta_ee",
                "jakarta_migration",
            }
        )

    # -- publish per destination mode --------------------------------------- #

    def _publish(
        self,
        store: MigrationReportStore,
        report: dict[str, Any],
        paths: WorkspacePaths,
        target_java: str,
    ) -> str:
        destination = report.get("destination") or {}
        mode = destination.get("mode", MODE_CREATE_NEW_REPO)
        commit_message = f"Migrate to Java {target_java} via OpenRewrite"

        if mode == MODE_LOCAL_FOLDER:
            store.append_logs(["Local destination: migrated code left in the workspace."])
            return str(paths.migrated_repo_dir)

        if mode == MODE_EXISTING_REPO_BRANCH:
            branch = destination.get("targetBranch") or "migration"
            source_url = report.get("sourceRepoUrl") or ""
            self._branch_creator.push_branch(
                paths.migrated_repo_dir, source_url, branch, commit_message=commit_message
            )
            return f"{source_url.rstrip('/').removesuffix('.git')}/tree/{branch}"

        # Default: create a new repo under the configured owner and push.
        created = self._repo_creator.create(
            destination.get("targetRepoName") or "",
            owner=destination.get("targetOwner"),
            host=destination.get("targetHost"),
        )
        self._repo_pusher.push(
            paths.migrated_repo_dir,
            created.clone_url,
            commit_message=commit_message,
            allow_force_update_existing=True,
        )
        return created.html_url

    # -- helpers ------------------------------------------------------------- #

    @staticmethod
    def _resolve_destination(config: dict[str, Any], connect: dict[str, Any]) -> dict[str, Any]:
        destination = dict(config.get("destination") or {})
        if destination.get("mode"):
            return destination
        # No saved config — default to a new repo under the configured owner.
        repo_name = connect.get("repoName") or "repo"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return {
            "mode": MODE_CREATE_NEW_REPO,
            "targetOwner": settings.github_target_owner,
            "targetHost": "github.com",
            "targetRepoName": f"{repo_name}-Migrated{timestamp}",
        }

    @staticmethod
    def _describe_migration_failure(result: MigrationRunResult) -> str:
        if result.tool_unavailable:
            return (
                f"OpenRewrite could not run: {result.tool.title()} tooling was "
                "not found in this environment."
            )
        if result.pre_recipe_failure:
            return (
                f"{result.tool.title()} failed while evaluating/compiling the "
                "project itself, before any OpenRewrite recipe ran. This is a "
                "project-level build configuration or plugin incompatibility "
                "(see the logs for the specific build error), not something a "
                "migration recipe can fix automatically -- it typically "
                "requires a manual fix in the source repository (e.g. "
                "removing or upgrading an incompatible plugin/dependency) "
                "before automated migration can proceed."
            )
        return "OpenRewrite migration failed. See logs for details."

    @staticmethod
    def _fail(store: MigrationReportStore, job_id: str, message: str) -> None:
        store.append_logs([f"ERROR: {message}"])
        store.update(
            status=MigrationStatus.FAILED.value,
            currentStep=MigrationStep.FAILED.value,
            errorMessage=message,
            completedAt=_now(),
        )
        logger.warning("Migration failed for job %s: %s", job_id, message)
