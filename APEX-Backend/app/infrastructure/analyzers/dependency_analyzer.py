"""Extracts declared dependencies from Maven or Gradle build files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree.ElementTree import Element

_GRADLE_CONFIGS = (
    "implementation",
    "api",
    "compileOnly",
    "compileOnlyApi",
    "runtimeOnly",
    "testImplementation",
    "testCompileOnly",
    "testRuntimeOnly",
    "annotationProcessor",
    "developmentOnly",
    "compile",  # legacy
    "testCompile",  # legacy
)


@dataclass(frozen=True)
class Dependency:
    group_id: str
    artifact_id: str
    version: str | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "groupId": self.group_id,
            "artifactId": self.artifact_id,
            "version": self.version,
        }


class DependencyAnalyzer:
    def analyze(
        self,
        pom_root: Element | None,
        build_gradle_text: str,
    ) -> list[Dependency]:
        if pom_root is not None:
            return self._from_maven(pom_root)
        if build_gradle_text:
            return self._from_gradle(build_gradle_text)
        return []

    # -- Maven --------------------------------------------------------------- #

    def _from_maven(self, pom_root: Element) -> list[Dependency]:
        properties = self._maven_properties(pom_root)
        dependencies_block = pom_root.find("dependencies")
        if dependencies_block is None:
            return []

        result: list[Dependency] = []
        for dependency in dependencies_block.findall("dependency"):
            group = self._text(dependency.find("groupId"))
            artifact = self._text(dependency.find("artifactId"))
            version = self._resolve(self._text(dependency.find("version")), properties)
            if group and artifact:
                result.append(Dependency(group, artifact, version or None))
        return result

    @staticmethod
    def _maven_properties(pom_root: Element) -> dict[str, str]:
        properties: dict[str, str] = {}
        block = pom_root.find("properties")
        if block is not None:
            for child in block:
                if child.text:
                    properties[child.tag] = child.text.strip()
        return properties

    @staticmethod
    def _resolve(version: str | None, properties: dict[str, str]) -> str | None:
        if not version:
            return None
        match = re.fullmatch(r"\$\{(.+?)\}", version.strip())
        if match:
            return properties.get(match.group(1))
        return version.strip()

    @staticmethod
    def _text(node: Element | None) -> str | None:
        return node.text.strip() if node is not None and node.text else None

    # -- Gradle -------------------------------------------------------------- #

    def _from_gradle(self, build_text: str) -> list[Dependency]:
        result: list[Dependency] = []
        seen: set[tuple[str, str]] = set()
        configs = "|".join(_GRADLE_CONFIGS)

        # configuration 'group:artifact:version'  /  configuration("group:artifact:version")
        pattern = re.compile(
            rf"\b(?:{configs})\s*[(\s]\s*['\"]([^'\"]+:[^'\"]+)['\"]",
        )
        for match in pattern.finditer(build_text):
            coordinate = match.group(1)
            parts = coordinate.split(":")
            if len(parts) < 2:
                continue
            group, artifact = parts[0], parts[1]
            version = parts[2] if len(parts) >= 3 else None
            key = (group, artifact)
            if key in seen:
                continue
            seen.add(key)
            result.append(Dependency(group, artifact, version))
        return result
