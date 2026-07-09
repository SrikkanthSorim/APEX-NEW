"""Maps a target Java version (+ Jakarta flag) to OpenRewrite recipes.

Scope per plan: Java version upgrade + optional javax->jakarta. Dependency /
vulnerability recipes are intentionally NOT included here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings

# UpgradeToJavaNN recipes provided by rewrite-migrate-java.
_JAVA_UPGRADE_RECIPES = [
    (21, "org.openrewrite.java.migrate.UpgradeToJava21"),
    (17, "org.openrewrite.java.migrate.UpgradeToJava17"),
    (11, "org.openrewrite.java.migrate.UpgradeToJava11"),
]
_JAKARTA_RECIPE = "org.openrewrite.java.migrate.jakarta.JavaxMigrationToJakarta"


@dataclass(frozen=True)
class RecipePlan:
    active_recipes: list[str] = field(default_factory=list)
    recipe_artifact: str = ""

    @property
    def has_recipes(self) -> bool:
        return bool(self.active_recipes)

    @property
    def active_recipes_csv(self) -> str:
        return ",".join(self.active_recipes)


def _parse_major(version: str | None) -> int | None:
    if not version:
        return None
    text = version.strip().lower().replace("java", "").strip()
    # "1.8" -> 8
    if text.startswith("1."):
        text = text.split(".", 1)[1]
    text = text.split(".", 1)[0]
    return int(text) if text.isdigit() else None


class RecipeMapper:
    def build_plan(self, target_java_version: str | None, *, include_jakarta: bool) -> RecipePlan:
        recipes: list[str] = []

        target = _parse_major(target_java_version)
        if target is not None:
            for threshold, recipe in _JAVA_UPGRADE_RECIPES:
                if target >= threshold:
                    recipes.append(recipe)
                    break  # highest applicable upgrade recipe only

        if include_jakarta:
            recipes.append(_JAKARTA_RECIPE)

        artifact = (
            f"org.openrewrite.recipe:rewrite-migrate-java:{settings.rewrite_migrate_java_version}"
        )
        return RecipePlan(active_recipes=recipes, recipe_artifact=artifact)
