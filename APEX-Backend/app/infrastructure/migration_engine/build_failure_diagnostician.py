"""Diagnoses a failed post-migration build and proposes additional recipes.

Matches build error lines against the catalog's ``errorSignalRecipes`` (data,
not per-framework Python conditionals), so the retry loop in
``StartMigrationUseCase`` can identify a probable root cause and expand the
OpenRewrite recipe plan instead of giving up after a single attempt. Pure
function -- no I/O, no subprocess calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.infrastructure.migration_engine.recipe_mapper import RecipeEntry

# Package prefixes that belong to the JDK itself, not a third-party
# dependency -- never worth an UpgradeDependencyVersion recipe.
_JDK_PACKAGE_PREFIXES = ("java.", "javax.", "jakarta.", "jdk.", "sun.", "com.sun.")


@dataclass(frozen=True)
class Diagnosis:
    id: str
    recipe_entry: RecipeEntry
    artifact_key: str
    reason: str


def diagnose(error_lines: list[str], catalog: dict[str, Any]) -> list[Diagnosis]:
    """Match build error lines against the catalog's error-signal recipes.

    Returns at most one :class:`Diagnosis` per matched signal id, in catalog
    order. A signal that matches but yields no actionable recipe (e.g. no
    resolvable dependency group) is skipped.
    """
    if not error_lines:
        return []
    text = "\n".join(error_lines)

    diagnoses: list[Diagnosis] = []
    seen_ids: set[str] = set()
    for rule in catalog.get("errorSignalRecipes", []):
        rule_id = str(rule.get("id") or "")
        pattern = rule.get("pattern")
        if not rule_id or rule_id in seen_ids or not pattern:
            continue
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        recipe_entry = _build_recipe_entry(rule, match)
        if recipe_entry is None:
            continue
        seen_ids.add(rule_id)
        diagnoses.append(
            Diagnosis(
                id=rule_id,
                recipe_entry=recipe_entry,
                artifact_key=str(rule.get("artifact") or ""),
                reason=str(rule.get("reason") or f"Matched build-failure signal '{rule_id}'"),
            )
        )
    return diagnoses


def _build_recipe_entry(rule: dict[str, Any], match: re.Match[str]) -> RecipeEntry | None:
    recipe = str(rule.get("recipe") or "").strip()
    if not recipe:
        return None

    if rule.get("groupFromMatch"):
        group = _extract_dependency_group(match)
        if not group:
            return None
        return {
            recipe: {
                "groupId": group,
                "artifactId": "*",
                "newVersion": str(rule.get("newVersionPattern") or "latest.release"),
            }
        }

    return recipe


def _extract_dependency_group(match: re.Match[str]) -> str | None:
    for candidate in match.groups():
        if not candidate:
            continue
        package = candidate.strip(".")
        if "." not in package:
            continue
        if any(package == prefix.rstrip(".") or package.startswith(prefix) for prefix in _JDK_PACKAGE_PREFIXES):
            continue
        # UpgradeDependencyVersion matches by groupId prefix/exact match; the
        # package's leading segments are the closest dynamic proxy we have
        # for the Maven/Gradle groupId without guessing a specific artifact.
        segments = package.split(".")
        return ".".join(segments[:2]) if len(segments) > 2 else package
    return None
