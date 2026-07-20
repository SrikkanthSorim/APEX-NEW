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


if __name__ == "__main__":
    unittest.main()
