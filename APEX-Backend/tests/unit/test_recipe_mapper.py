import unittest

from app.infrastructure.migration_engine.recipe_mapper import (
    MigrationRecipeContext,
    RecipeMapper,
)


class RecipeMapperTests(unittest.TestCase):
    def test_junit_recipe_is_not_selected_for_java_migration_by_default(self) -> None:
        mapper = RecipeMapper(
            {
                "recipeArtifacts": {"testing": "testing-artifact"},
                "conditionalRecipes": [
                    {
                        "id": "junit4-to-5",
                        "whenFramework": ["junit"],
                        "whenConversion": ["test_migration", "junit4_to_5"],
                        "recipe": "org.openrewrite.java.testing.junit5.JUnit5BestPractices",
                        "artifact": "testing",
                    }
                ],
            }
        )
        context = MigrationRecipeContext(
            source_java_version="17",
            target_java_version="17",
            build_tool="MAVEN",
            frameworks=["junit"],
            conversion_types=["java_version"],
        )

        plan = mapper.build_plan("17", include_jakarta=False, context=context)

        self.assertNotIn(
            "org.openrewrite.java.testing.junit5.JUnit5BestPractices",
            plan.active_recipes,
        )

    def test_junit_recipe_is_selected_when_test_migration_is_requested(self) -> None:
        mapper = RecipeMapper(
            {
                "recipeArtifacts": {"testing": "testing-artifact"},
                "conditionalRecipes": [
                    {
                        "id": "junit4-to-5",
                        "whenFramework": ["junit"],
                        "whenConversion": ["test_migration", "junit4_to_5"],
                        "recipe": "org.openrewrite.java.testing.junit5.JUnit5BestPractices",
                        "artifact": "testing",
                    }
                ],
            }
        )
        context = MigrationRecipeContext(
            source_java_version="17",
            target_java_version="17",
            build_tool="MAVEN",
            frameworks=["junit"],
            conversion_types=["test_migration"],
        )

        plan = mapper.build_plan("17", include_jakarta=False, context=context)

        self.assertIn(
            "org.openrewrite.java.testing.junit5.JUnit5BestPractices",
            plan.active_recipes,
        )

    def test_plain_java_upgrade_does_not_require_spring_boot(self) -> None:
        mapper = RecipeMapper(
            {
                "recipeArtifacts": {"java": "java-artifact", "spring": "spring-artifact"},
                "javaUpgradeRecipes": [
                    {
                        "minTarget": 17,
                        "recipe": "org.openrewrite.java.migrate.UpgradeToJava17",
                        "artifact": "java",
                    }
                ],
                "springBootRecipeLadder": {
                    "legacy": ["org.openrewrite.java.spring.boot2.UpgradeSpringBoot_2_7"],
                    "artifact": "spring",
                    "whenFramework": ["spring-boot"],
                },
            }
        )
        context = MigrationRecipeContext(
            source_java_version="8",
            target_java_version="17",
            build_tool="MAVEN",
            frameworks=[],
            conversion_types=["java_version"],
        )

        plan = mapper.build_plan("17", include_jakarta=False, context=context)

        self.assertIn("org.openrewrite.java.migrate.UpgradeToJava17", plan.active_recipes)
        self.assertIn("org.openrewrite.java.migrate.UpgradeJavaVersion", plan.active_recipes)
        self.assertNotIn(
            "org.openrewrite.java.spring.boot2.UpgradeSpringBoot_2_7",
            plan.active_recipes,
        )

    def test_spring_boot_recipe_requires_spring_boot_framework(self) -> None:
        mapper = RecipeMapper(
            {
                "recipeArtifacts": {"spring": "spring-artifact"},
                "springBootRecipeLadder": {
                    "legacy": ["org.openrewrite.java.spring.boot2.UpgradeSpringBoot_2_7"],
                    "artifact": "spring",
                    "whenFramework": ["spring-boot"],
                },
            }
        )
        context = MigrationRecipeContext(
            source_java_version="8",
            target_java_version="11",
            build_tool="GRADLE",
            frameworks=["spring-framework"],
            conversion_types=["spring_boot"],
        )

        plan = mapper.build_plan(
            "11",
            include_jakarta=False,
            context=context,
            include_java_upgrade=False,
            include_conditional=False,
            include_spring_boot=True,
            include_dependency_currency=False,
            include_cleanup=False,
        )

        self.assertEqual(plan.active_recipes, [])


if __name__ == "__main__":
    unittest.main()
