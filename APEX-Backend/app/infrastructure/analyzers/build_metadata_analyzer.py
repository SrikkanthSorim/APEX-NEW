"""Detect build plugins, imported BOMs, and framework signals."""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree.ElementTree import Element

from app.infrastructure.analyzers.dependency_analyzer import Dependency


@dataclass(frozen=True)
class BuildPlugin:
    id: str
    version: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"id": self.id, "version": self.version}


@dataclass(frozen=True)
class BomVersion:
    group_id: str
    artifact_id: str
    version: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "groupId": self.group_id,
            "artifactId": self.artifact_id,
            "version": self.version,
        }


class BuildMetadataAnalyzer:
    def detect_plugins(self, pom_root: Element | None, build_gradle_text: str) -> list[BuildPlugin]:
        if pom_root is not None:
            return self._maven_plugins(pom_root)
        return self._gradle_plugins(build_gradle_text)

    def detect_boms(self, pom_root: Element | None, build_gradle_text: str) -> list[BomVersion]:
        if pom_root is not None:
            return self._maven_boms(pom_root)
        return self._gradle_boms(build_gradle_text)

    def detect_frameworks(
        self,
        *,
        spring_boot_version: str | None,
        dependencies: list[Dependency],
        build_gradle_text: str,
    ) -> list[str]:
        frameworks: set[str] = set()
        coordinates = {
            f"{dependency.group_id}:{dependency.artifact_id}".lower()
            for dependency in dependencies
        }
        groups = {dependency.group_id.lower() for dependency in dependencies}

        if spring_boot_version or any(item.startswith("org.springframework.boot:") for item in coordinates):
            frameworks.add("spring-boot")
        if "org.springframework" in groups:
            frameworks.add("spring-framework")
        if any("spring-security" in item for item in coordinates):
            frameworks.add("spring-security")
        if any(item.startswith("org.hibernate") for item in groups):
            frameworks.add("hibernate")
        if any(item.startswith("jakarta.") for item in groups):
            frameworks.add("jakarta-ee")
        if any(item.startswith("javax.") for item in groups):
            frameworks.add("javax-ee")
        if "org.junit.jupiter:junit-jupiter" in coordinates or "junit:junit" in coordinates:
            frameworks.add("junit")
        if "org.springframework.boot" in build_gradle_text:
            frameworks.add("spring-boot")

        return sorted(frameworks)

    # -- Maven --------------------------------------------------------------- #

    @staticmethod
    def _maven_plugins(pom_root: Element) -> list[BuildPlugin]:
        plugins: list[BuildPlugin] = []
        seen: set[str] = set()
        for plugin in pom_root.iter("plugin"):
            group = _text(plugin.find("groupId")) or "org.apache.maven.plugins"
            artifact = _text(plugin.find("artifactId"))
            version = _text(plugin.find("version"))
            if not artifact:
                continue
            plugin_id = f"{group}:{artifact}"
            if plugin_id in seen:
                continue
            seen.add(plugin_id)
            plugins.append(BuildPlugin(plugin_id, version))
        return plugins

    @staticmethod
    def _maven_boms(pom_root: Element) -> list[BomVersion]:
        boms: list[BomVersion] = []
        dependency_management = pom_root.find("dependencyManagement")
        if dependency_management is None:
            return boms
        dependencies = dependency_management.find("dependencies")
        if dependencies is None:
            return boms
        for dependency in dependencies.findall("dependency"):
            dep_type = _text(dependency.find("type"))
            scope = _text(dependency.find("scope"))
            if dep_type != "pom" or scope != "import":
                continue
            group = _text(dependency.find("groupId"))
            artifact = _text(dependency.find("artifactId"))
            if group and artifact:
                boms.append(BomVersion(group, artifact, _text(dependency.find("version"))))
        return boms

    # -- Gradle -------------------------------------------------------------- #

    @staticmethod
    def _gradle_plugins(build_text: str) -> list[BuildPlugin]:
        plugins: list[BuildPlugin] = []
        seen: set[str] = set()
        patterns = [
            r"id\s*[( ]\s*['\"]([^'\"]+)['\"]\)?\s*(?:version\s*['\"]([^'\"]+)['\"])?",
            r"classpath\s*[( ]\s*['\"][^:'\"]+:([^:'\"]+):([^'\"]+)['\"]",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, build_text):
                plugin_id = match.group(1)
                version = match.group(2) if match.lastindex and match.lastindex >= 2 else None
                if plugin_id in seen:
                    continue
                seen.add(plugin_id)
                plugins.append(BuildPlugin(plugin_id, version))
        return plugins

    @staticmethod
    def _gradle_boms(build_text: str) -> list[BomVersion]:
        boms: list[BomVersion] = []
        patterns = [
            r"platform\s*[( ]\s*['\"]([^:'\"]+):([^:'\"]+):([^'\"]+)['\"]",
            r"mavenBom\s*[( ]\s*['\"]([^:'\"]+):([^:'\"]+):([^'\"]+)['\"]",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, build_text):
                boms.append(BomVersion(match.group(1), match.group(2), match.group(3)))
        return boms


def _text(node: Element | None) -> str | None:
    return node.text.strip() if node is not None and node.text else None
