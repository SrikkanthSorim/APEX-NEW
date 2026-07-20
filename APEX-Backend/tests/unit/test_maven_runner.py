import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from app.infrastructure.build import maven_runner
from app.infrastructure.build.maven_runner import MavenRewriteRunner
from app.infrastructure.migration_engine.recipe_mapper import RecipePlan
from app.shared.command_runner import CommandResult


class MavenRewriteRunnerTests(unittest.TestCase):
    def test_uses_run_no_fork_with_absolute_config(self) -> None:
        captured: dict[str, object] = {}

        def fake_run_command(command, *, cwd=None, timeout=None, env=None):
            config_arg = next(arg for arg in command if arg.startswith("-Drewrite.configLocation="))
            config_path = Path(config_arg.split("=", 1)[1])

            captured["command"] = command
            captured["cwd"] = cwd
            captured["config_path"] = config_path
            captured["config_text"] = config_path.read_text(encoding="utf-8")

            return CommandResult(command=command, exit_code=0, stdout="[INFO] BUILD SUCCESS", stderr="")

        plan = RecipePlan(
            recipe_list=["org.openrewrite.java.RemoveUnusedImports"],
            recipe_artifacts=["org.openrewrite.recipe:rewrite-migrate-java:latest.release"],
        )

        project_path = Path(__file__).resolve().parent / ".tmp-maven-runner"
        if project_path.exists():
            shutil.rmtree(project_path)
        project_path.mkdir()
        try:
            with (
                patch.object(maven_runner, "resolve_executable", return_value="mvn.cmd"),
                patch.object(maven_runner, "build_tool_env", return_value={"JAVA_HOME": "test"}),
                patch.object(maven_runner, "run_command", side_effect=fake_run_command),
            ):
                result = MavenRewriteRunner().run(project_path, plan, target_major=25)

            command = captured["command"]
            config_path = captured["config_path"]

            self.assertTrue(result.succeeded)
            self.assertTrue(any(str(arg).endswith(":runNoFork") for arg in command))
            self.assertIn("-Drewrite.activeRecipes=com.javaapex.DynamicMigration", command)
            self.assertEqual(Path(captured["cwd"]), project_path)
            self.assertTrue(config_path.is_absolute())
            self.assertIn("name: com.javaapex.DynamicMigration", captured["config_text"])
            self.assertIn("org.openrewrite.java.RemoveUnusedImports", captured["config_text"])
            self.assertFalse(config_path.exists())
        finally:
            shutil.rmtree(project_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
