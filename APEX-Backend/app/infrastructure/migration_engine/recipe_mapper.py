"""Catalog-backed OpenRewrite recipe selection.

Builds a *declarative* OpenRewrite recipe (a ``recipeList`` of recipe class
names and/or ``{recipe: {options}}`` entries) instead of a flat CSV of
zero-argument recipe names. This is what lets OpenRewrite itself resolve
version numbers at run time -- ``UpgradeJavaVersion.version`` is always the
user's exact selected target, and dependency/plugin bumps use OpenRewrite's
own dynamic version-pattern tokens (``latest.release``/``latest.patch``)
rather than a version we pinned in code or JSON.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

RecipeEntry = str | dict[str, dict[str, Any]]
# (recipe entry, artifact catalog key, human-readable selection reason)
ExtraRecipe = tuple[RecipeEntry, str, str]

_DECLARATIVE_RECIPE_NAME = "com.javaapex.DynamicMigration"


@dataclass(frozen=True)
class RecipePlan:
    recipe_list: list[RecipeEntry] = field(default_factory=list)
    recipe_artifacts: list[str] = field(default_factory=list)
    selection_reasons: list[str] = field(default_factory=list)

    @property
    def has_recipes(self) -> bool:
        return bool(self.recipe_list)

    @property
    def active_recipes(self) -> list[str]:
        """Flat recipe class names (no options) -- for logging/reporting."""
        names: list[str] = []
        for entry in self.recipe_list:
            name = recipe_entry_name(entry)
            if name not in names:
                names.append(name)
        return names

    @property
    def recipe_artifact(self) -> str:
        return ",".join(self.recipe_artifacts)

    @property
    def declarative_recipe_name(self) -> str:
        return _DECLARATIVE_RECIPE_NAME

    def to_declarative_yaml(self) -> str:
        """Render this plan as a standalone OpenRewrite declarative recipe.

        Written to a temp file and passed to the Maven/Gradle runners via
        ``rewrite.configLocation`` / ``rewrite.configFile`` so parameterized
        recipes (exact Java version, dependency GAVs, version patterns) can be
        activated without a hardcoded CSV of zero-arg recipe names.
        """
        lines = [
            "type: specs.openrewrite.org/v1beta/recipe",
            f"name: {_DECLARATIVE_RECIPE_NAME}",
            "displayName: JavaApex dynamic migration",
            "recipeList:",
        ]
        for entry in self.recipe_list:
            if isinstance(entry, str):
                lines.append(f"  - {entry}")
                continue
            ((recipe_name, options),) = entry.items()
            lines.append(f"  - {recipe_name}:")
            for key, value in options.items():
                lines.append(f"      {key}: {_yaml_scalar(value)}")
        return "\n".join(lines) + "\n"


def recipe_entry_name(entry: RecipeEntry) -> str:
    """The recipe class name for a plain or parameterized recipe entry."""
    return entry if isinstance(entry, str) else next(iter(entry))


def load_catalog() -> dict[str, Any]:
    """Load the OpenRewrite recipe catalog (shared with the diagnostician)."""
    return RecipeMapper._load_catalog()


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9_.\-]+", text):
        return text
    return json.dumps(text)


def _parse_major(version: str | None) -> int | None:
    if not version:
        return None
    text = version.strip().lower().replace("java", "").strip()
    # "1.8" -> 8
    if text.startswith("1."):
        text = text.split(".", 1)[1]
    text = text.split(".", 1)[0]
    return int(text) if text.isdigit() else None


@dataclass(frozen=True)
class MigrationRecipeContext:
    source_java_version: str | None
    target_java_version: str | None
    build_tool: str
    frameworks: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    build_plugins: list[str] = field(default_factory=list)
    bom_versions: list[str] = field(default_factory=list)
    conversion_types: list[str] = field(default_factory=list)


class RecipeMapper:
    def __init__(self, catalog: dict[str, Any] | None = None) -> None:
        self._catalog = catalog or self._load_catalog()

    def build_plan(
        self,
        target_java_version: str | None,
        *,
        include_jakarta: bool,
        context: MigrationRecipeContext | None = None,
        extra_recipes: list[ExtraRecipe] | None = None,
        include_java_upgrade: bool = True,
        include_conditional: bool = True,
        include_spring_boot: bool = True,
        include_dependency_currency: bool = True,
        include_cleanup: bool = True,
        cleanup_only: bool = False,
    ) -> RecipePlan:
        if context is None:
            context = MigrationRecipeContext(
                source_java_version=None,
                target_java_version=target_java_version,
                build_tool="",
                conversion_types=["jakarta"] if include_jakarta else [],
            )

        recipes: list[RecipeEntry] = []
        artifacts: list[str] = []
        reasons: list[str] = []

        target = _parse_major(target_java_version)
        source = _parse_major(context.source_java_version)
        if include_java_upgrade and target is not None and (source is None or source < target):
            rule = self._select_java_rule(target)
            if rule:
                self._append_recipe(rule.get("recipe", ""), rule.get("artifact", ""), recipes, artifacts)
                reasons.append(
                    f"Selected Java recipe for target {target}: {rule.get('recipe')}"
                )
            # Always assert the exact user-selected target, dynamically -- the
            # composite recipe above only exists for known majors and may be
            # older than what was requested (e.g. target 25 with only
            # UpgradeToJava21 available upstream).
            self._append_recipe(
                {"org.openrewrite.java.migrate.UpgradeJavaVersion": {"version": target}},
                "java",
                recipes,
                artifacts,
            )
            reasons.append(f"Asserting exact target Java version {target} via UpgradeJavaVersion")
        elif include_java_upgrade and target is not None:
            reasons.append(
                f"Source Java {source} already meets target {target}; no Java-version upgrade recipe needed."
            )

        if include_conditional:
            for rule in self._catalog.get("conditionalRecipes", []):
                if self._matches_rule(rule, context, target, include_jakarta):
                    self._append_recipe(rule.get("recipe", ""), rule.get("artifact", ""), recipes, artifacts)
                    reasons.append(f"Selected conditional recipe {rule.get('id')}: {rule.get('recipe')}")

        if include_spring_boot:
            spring_recipe = self._select_spring_boot_recipe(context, target, include_jakarta)
            if spring_recipe:
                ladder = self._catalog.get("springBootRecipeLadder") or {}
                self._append_recipe(spring_recipe, ladder.get("artifact", "spring"), recipes, artifacts)
                reasons.append(f"Selected Spring Boot upgrade recipe: {spring_recipe}")

        if include_dependency_currency:
            for entry, artifact_key, reason in self._dependency_currency_entries(context):
                self._append_recipe(entry, artifact_key, recipes, artifacts)
                reasons.append(reason)

        for entry, artifact_key, reason in extra_recipes or []:
            self._append_recipe(entry, artifact_key, recipes, artifacts)
            reasons.append(reason)

        if include_cleanup and (recipes or cleanup_only):
            for rule in self._catalog.get("cleanupRecipes", []):
                self._append_recipe(rule.get("recipe", ""), rule.get("artifact", ""), recipes, artifacts)
                reasons.append(f"Selected cleanup recipe {rule.get('id')}: {rule.get('recipe')}")

        return RecipePlan(
            recipe_list=recipes,
            recipe_artifacts=artifacts,
            selection_reasons=reasons,
        )

    def dependency_currency_artifact_key(self) -> str:
        return str((self._catalog.get("dependencyCurrencyGroups") or {}).get("artifact") or "dependencies")

    @staticmethod
    def _load_catalog() -> dict[str, Any]:
        try:
            return json.loads(settings.openrewrite_recipe_catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _select_java_rule(self, target: int) -> dict[str, Any] | None:
        rules = [
            rule for rule in self._catalog.get("javaUpgradeRecipes", [])
            if int(rule.get("minTarget", 0) or 0) <= target
        ]
        if not rules:
            return None
        return max(rules, key=lambda rule: int(rule.get("minTarget", 0) or 0))

    def _select_spring_boot_recipe(
        self,
        context: MigrationRecipeContext,
        target: int | None,
        include_jakarta: bool,
    ) -> str | None:
        ladder = self._catalog.get("springBootRecipeLadder") or {}
        when_framework = {str(item).lower() for item in ladder.get("whenFramework", [])}
        frameworks = {item.lower() for item in context.frameworks}
        if when_framework and not (when_framework & frameworks):
            return None

        jakarta_min_target = int(ladder.get("jakartaMinTarget", 17) or 17)
        use_jakarta_line = include_jakarta or (target is not None and target >= jakarta_min_target)
        candidates = ladder.get("jakarta" if use_jakarta_line else "legacy") or []
        # Newest-first list in the catalog; the first entry is the highest
        # available recipe for that line -- OpenRewrite's own recipe chains
        # from whatever Spring Boot version the project currently declares.
        return str(candidates[0]) if candidates else None

    def _dependency_currency_entries(self, context: MigrationRecipeContext) -> list[ExtraRecipe]:
        config = self._catalog.get("dependencyCurrencyGroups") or {}
        frameworks_map: dict[str, list[str]] = config.get("frameworks") or {}
        if not frameworks_map:
            return []
        recipe_class = str(config.get("recipe") or "org.openrewrite.java.dependencies.UpgradeDependencyVersion")
        new_version = str(config.get("newVersionPattern") or "latest.patch")
        artifact_key = str(config.get("artifact") or "dependencies")
        frameworks = {item.lower() for item in context.frameworks}

        wanted_groups: set[str] = set()
        for framework_name, groups in frameworks_map.items():
            if framework_name.lower() in frameworks:
                wanted_groups.update(str(group).lower() for group in groups)
        if not wanted_groups:
            return []

        entries: list[ExtraRecipe] = []
        seen: set[tuple[str, str]] = set()
        for coordinate in context.dependencies:
            group, _, artifact = coordinate.partition(":")
            if not group or not artifact or group.lower() not in wanted_groups:
                continue
            if (group, artifact) in seen:
                continue
            seen.add((group, artifact))
            entries.append((
                {recipe_class: {"groupId": group, "artifactId": artifact, "newVersion": new_version}},
                artifact_key,
                f"Dependency currency bump for {group}:{artifact} -> {new_version}",
            ))
        return entries

    def _append_recipe(
        self,
        entry: RecipeEntry,
        artifact_key: str,
        recipes: list[RecipeEntry],
        artifacts: list[str],
    ) -> None:
        if isinstance(entry, str) and not entry.strip():
            return
        if entry not in recipes:
            recipes.append(entry)
        artifact = self._artifact(artifact_key)
        if artifact and artifact not in artifacts:
            artifacts.append(artifact)

    def _artifact(self, key: str) -> str:
        if not key:
            return ""
        raw = self._catalog.get("recipeArtifacts", {}).get(key, key)
        return (
            str(raw)
            .replace("${rewrite_migrate_java_version}", settings.rewrite_migrate_java_version)
            .replace("${rewrite_spring_version}", settings.rewrite_spring_version)
            .replace("${rewrite_java_dependencies_version}", settings.rewrite_java_dependencies_version)
            .replace("${rewrite_testing_frameworks_version}", settings.rewrite_testing_frameworks_version)
        )

    @staticmethod
    def _matches_rule(
        rule: dict[str, Any],
        context: MigrationRecipeContext,
        target: int | None,
        include_jakarta: bool,
    ) -> bool:
        min_target = rule.get("whenMinTarget")
        if min_target is not None and (target is None or target < int(min_target)):
            return False

        framework_filter = {str(item).lower() for item in rule.get("whenFramework", [])}
        frameworks = {item.lower() for item in context.frameworks}
        if framework_filter and not (framework_filter & frameworks):
            return False

        conversion_filter = {str(item).lower() for item in rule.get("whenConversion", [])}
        conversions = {item.lower() for item in context.conversion_types}
        if conversion_filter and not (conversion_filter & conversions):
            return False

        if rule.get("id") == "jakarta-ee" and not include_jakarta:
            return False
        return True
