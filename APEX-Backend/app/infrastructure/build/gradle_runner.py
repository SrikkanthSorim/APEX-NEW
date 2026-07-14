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

import os
import shutil
import uuid
from pathlib import Path

from app.core.config import settings
from app.infrastructure.java_runtime import build_tool_env, gradle_runtime_major, resolve_gradle_executable
from app.infrastructure.migration_engine.recipe_mapper import RecipePlan
from app.shared.command_runner import CommandResult, run_command

_WRAPPER_NAME = "gradlew.bat" if os.name == "nt" else "gradlew"


class GradleNotAvailableError(RuntimeError):
    pass


class GradleRewriteRunner:
    def is_available(self, project_dir: Path) -> bool:
        return self._resolve_gradle(project_dir) is not None

    def run(self, project_dir: Path, plan: RecipePlan, target_major: int | None = None) -> CommandResult:
        project_dir = project_dir.resolve()
        gradle = self._resolve_gradle(project_dir)
        if not gradle:
            raise GradleNotAvailableError("Gradle (wrapper or system) was not found.")

        run_id = uuid.uuid4().hex
        config_path = (project_dir / f".javaapex-rewrite-{run_id}.yml").resolve()
        config_path.write_text(plan.to_declarative_yaml(), encoding="utf-8")
        init_script = self._write_init_script(project_dir, plan, config_path, run_id)
        launcher, launch_dir = self._resolve_launcher(project_dir, gradle, run_id)
        try:
            command = [
                launcher,
                "--project-dir",
                str(project_dir),
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
                env=self._build_env(project_dir, target_major),
            )
        finally:
            for temp_file in (init_script, config_path):
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            if launch_dir is not None:
                shutil.rmtree(launch_dir, ignore_errors=True)

    # -- helpers ------------------------------------------------------------- #

    @staticmethod
    def _resolve_launcher(project_dir: Path, gradle: str, run_id: str) -> tuple[str, Path | None]:
        """Avoid launching the project's own wrapper script in place.

        The recipe run itself can include ``UpdateGradleWrapper``, which
        rewrites ``gradlew``/``gradlew.bat`` on disk. If that's also the
        script currently being interpreted (Windows cmd.exe reads a running
        ``.bat`` file by byte offset as it executes), the in-place rewrite
        corrupts the interpreter's read position: the underlying Gradle build
        finishes successfully, but the shell then resumes reading garbage
        from the now-different file and exits non-zero, reporting a failure
        for a migration that actually succeeded. Launching an isolated copy
        of the wrapper (pointed back at the real project via
        ``--project-dir``) lets the recipe freely rewrite the project's own
        wrapper files without touching the script actually running.
        """
        wrapper = project_dir / _WRAPPER_NAME
        if Path(gradle).resolve() != wrapper.resolve():
            return gradle, None

        launch_dir = project_dir.parent / ".javaapex-gradle" / f"wrapper-launch-{run_id}"
        launch_dir.mkdir(parents=True, exist_ok=True)
        copied_wrapper = launch_dir / _WRAPPER_NAME
        shutil.copy2(wrapper, copied_wrapper)
        if os.name != "nt":
            copied_wrapper.chmod(0o755)
        wrapper_jar_dir = project_dir / "gradle" / "wrapper"
        if wrapper_jar_dir.is_dir():
            shutil.copytree(wrapper_jar_dir, launch_dir / "gradle" / "wrapper")
        return str(copied_wrapper), launch_dir

    @staticmethod
    def _resolve_gradle(project_dir: Path) -> str | None:
        return resolve_gradle_executable(project_dir)

    def _build_env(self, project_dir: Path, target_major: int | None) -> dict[str, str]:
        runtime_major = gradle_runtime_major(project_dir, target_major)
        env = build_tool_env(runtime_major)

        # Keep Gradle/OpenRewrite caches out of the user's home directory and
        # out of migrated-repo (repo_pusher commits everything under it).
        # GRADLE_USER_HOME is shared across all jobs (not per-job) so the
        # Gradle distribution zip and dependency/plugin caches are downloaded
        # once and reused -- Gradle already supports concurrent local builds
        # sharing one user home via its own cache locking. java-user-home
        # stays per-job since it's only a throwaway -Duser.home target.
        cache_root = project_dir.parent / ".javaapex-gradle"
        gradle_home = settings.gradle_shared_cache_dir
        java_user_home = cache_root / "java-user-home"
        gradle_home.mkdir(parents=True, exist_ok=True)
        java_user_home.mkdir(parents=True, exist_ok=True)

        env["GRADLE_USER_HOME"] = str(gradle_home)
        # Gradle's wrapper bootstrap (the distribution zip download) uses a
        # short default socket/connection timeout, which is what actually
        # trips on a slow link even though the cache above avoids repeating
        # the download in the common case. Raise it defensively for the
        # first-time-per-version download.
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
