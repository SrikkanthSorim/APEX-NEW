"""Detects the project's Java (source) version.

Read-only inspection of Maven ``pom.xml`` properties / compiler-plugin config,
or Gradle source/target compatibility and toolchain settings. Returns a
normalized major version string (e.g. ``"8"``, ``"11"``, ``"17"``) or
``"UNKNOWN"``.
"""

from __future__ import annotations

import re
from xml.etree.ElementTree import Element

UNKNOWN = "UNKNOWN"


def normalize_java_version(raw: str | None) -> str | None:
    """Normalize ``"1.8"`` -> ``"8"``, strip prefixes, keep ``"11"``/``"17"`` etc."""
    if not raw:
        return None
    value = raw.strip()
    # JavaVersion.VERSION_1_8 / VERSION_17
    match = re.search(r"VERSION_(\d+)(?:_(\d+))?", value)
    if match:
        major, minor = match.group(1), match.group(2)
        value = f"{major}.{minor}" if major == "1" and minor else major
    # JavaLanguageVersion.of(17)
    match = re.search(r"of\((\d+)\)", value)
    if match:
        return match.group(1)
    value = value.strip("\"'")
    # 1.8 -> 8, 1.7 -> 7
    dotted = re.match(r"^1\.(\d+)$", value)
    if dotted:
        return dotted.group(1)
    simple = re.match(r"^(\d+)$", value)
    if simple:
        return simple.group(1)
    return None


class JavaVersionDetector:
    def detect(
        self,
        build_tool: str,
        pom_root: Element | None,
        build_gradle_text: str,
        gradle_properties_text: str,
    ) -> str:
        if pom_root is not None:
            version = self._from_maven(pom_root)
            if version:
                return version
        if build_gradle_text or gradle_properties_text:
            version = self._from_gradle(build_gradle_text, gradle_properties_text)
            if version:
                return version
        return UNKNOWN

    # -- Maven --------------------------------------------------------------- #

    def _from_maven(self, pom_root: Element) -> str | None:
        properties = pom_root.find("properties")
        if properties is not None:
            for key in (
                "maven.compiler.release",
                "maven.compiler.source",
                "maven.compiler.target",
                "java.version",
            ):
                child = properties.find(key)
                if child is not None and child.text:
                    normalized = normalize_java_version(child.text)
                    if normalized:
                        return normalized

        # maven-compiler-plugin <configuration><source|target|release>
        for plugin in pom_root.iter("plugin"):
            artifact = plugin.find("artifactId")
            if artifact is None or artifact.text != "maven-compiler-plugin":
                continue
            config = plugin.find("configuration")
            if config is None:
                continue
            for tag in ("release", "source", "target"):
                node = config.find(tag)
                if node is not None and node.text:
                    normalized = normalize_java_version(node.text)
                    if normalized:
                        return normalized
        return None

    # -- Gradle -------------------------------------------------------------- #

    def _from_gradle(self, build_text: str, properties_text: str) -> str | None:
        patterns = [
            r"languageVersion\s*=?\s*JavaLanguageVersion\.of\((\d+)\)",
            r"sourceCompatibility\s*=?\s*['\"]?([\w.]+)['\"]?",
            r"targetCompatibility\s*=?\s*['\"]?([\w.]+)['\"]?",
        ]
        for pattern in patterns:
            match = re.search(pattern, build_text)
            if match:
                normalized = normalize_java_version(match.group(1))
                if normalized:
                    return normalized

        match = re.search(r"(?:java|source)Version\s*=\s*([\w.]+)", properties_text)
        if match:
            return normalize_java_version(match.group(1))
        return None
