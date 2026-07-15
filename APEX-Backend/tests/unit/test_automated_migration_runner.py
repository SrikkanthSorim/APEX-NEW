import shutil
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from app.infrastructure.migration_engine.automated_migration_runner import (
    AutomatedMigrationRunner,
)
from app.infrastructure.migration_engine.recipe_mapper import RecipeMapper
from app.shared.command_runner import CommandResult


def _analysis(*, source_java: str = "8", frameworks: list[str] | None = None):
    return SimpleNamespace(
        current_java_version=source_java,
        spring_boot_version=None,
        frameworks=frameworks or [],
        dependencies=[],
        build_plugins=[],
        bom_versions=[],
    )


class _FakeAnalyzer:
    def __init__(self, analysis):
        self._analysis = analysis

    def analyze(self, _project_dir: Path):
        return self._analysis


class _FakeSanitizer:
    def sanitize_project(self, _project_dir: Path):
        return []


class _FakeGradlePreflight:
    def modernize(self, _project_dir: Path, _target_major: int | None):
        return []


class _FakeMaven:
    def __init__(self, *, fail_recipe: str | None = None):
        self.fail_recipe = fail_recipe
        self.runs: list[list[str]] = []

    def run(self, _project_dir: Path, plan, _target_major: int | None):
        recipes = plan.active_recipes
        self.runs.append(recipes)
        if self.fail_recipe and self.fail_recipe in recipes:
            return CommandResult(
                command=["mvn"],
                exit_code=1,
                stdout=(
                    "[INFO] Using active recipe(s) [com.javaapex.DynamicMigration]\n"
                    "[ERROR] The recipe produced an error."
                ),
                stderr="",
            )
        return CommandResult(
            command=["mvn"],
            exit_code=0,
            stdout="[INFO] Using active recipe(s) [com.javaapex.DynamicMigration]",
            stderr="",
        )


class AutomatedMigrationRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(__file__).resolve().parent / f".tmp-runner-{uuid.uuid4().hex}"
        self.tmp.mkdir(parents=True)
        (self.tmp / "pom.xml").write_text("<project />", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _runner(self, *, analysis, fake_maven: _FakeMaven) -> AutomatedMigrationRunner:
        runner = AutomatedMigrationRunner()
        runner._project_analyzer = _FakeAnalyzer(analysis)  # noqa: SLF001
        runner._pom_sanitizer = _FakeSanitizer()  # noqa: SLF001
        runner._gradle_preflight = _FakeGradlePreflight()  # noqa: SLF001
        runner._maven = fake_maven  # noqa: SLF001
        runner._recipe_mapper = RecipeMapper(  # noqa: SLF001
            {
                "recipeArtifacts": {
                    "java": "java-artifact",
                    "testing": "testing-artifact",
                    "core": "",
                },
                "javaUpgradeRecipes": [
                    {
                        "minTarget": 17,
                        "recipe": "org.openrewrite.java.migrate.UpgradeToJava17",
                        "artifact": "java",
                    }
                ],
                "conditionalRecipes": [
                    {
                        "id": "junit4-to-5",
                        "whenFramework": ["junit"],
                        "whenConversion": ["test_migration"],
                        "recipe": "org.openrewrite.java.testing.junit5.JUnit5BestPractices",
                        "artifact": "testing",
                    }
                ],
                "cleanupRecipes": [
                    {
                        "id": "remove-unused-imports",
                        "recipe": "org.openrewrite.java.RemoveUnusedImports",
                        "artifact": "core",
                    }
                ],
            }
        )
        return runner

    def test_optional_test_migration_failure_is_skipped(self) -> None:
        fake_maven = _FakeMaven(
            fail_recipe="org.openrewrite.java.testing.junit5.JUnit5BestPractices"
        )
        runner = self._runner(
            analysis=_analysis(frameworks=["junit"]),
            fake_maven=fake_maven,
        )

        result = runner.run(
            self.tmp,
            "MAVEN",
            "17",
            include_jakarta=False,
            conversion_types=["java_version", "test_migration"],
        )

        self.assertTrue(result.success)
        self.assertIn("org.openrewrite.java.migrate.UpgradeToJava17", result.recipes)
        self.assertNotIn(
            "org.openrewrite.java.testing.junit5.JUnit5BestPractices",
            result.recipes,
        )
        self.assertEqual(result.skipped_recipes[0]["phase"], "test-migration")
        self.assertTrue(
            any(phase["status"] == "skipped" for phase in result.phase_results)
        )

    def test_core_java_migration_failure_is_fatal(self) -> None:
        fake_maven = _FakeMaven(
            fail_recipe="org.openrewrite.java.migrate.UpgradeToJava17"
        )
        runner = self._runner(
            analysis=_analysis(frameworks=[]),
            fake_maven=fake_maven,
        )

        result = runner.run(
            self.tmp,
            "MAVEN",
            "17",
            include_jakarta=False,
            conversion_types=["java_version"],
        )

        self.assertFalse(result.success)
        self.assertIn("org.openrewrite.java.migrate.UpgradeToJava17", result.recipes)


if __name__ == "__main__":
    unittest.main()
