"""Detects the (non-Boot) Spring Framework version from real project files.

Used for traditional ``org.springframework`` projects (spring-core,
spring-context, spring-webmvc, spring-beans, ...) that do not use Spring Boot.
Returns the version string when found, otherwise ``None``.
"""

from __future__ import annotations

import re
from xml.etree.ElementTree import Element

_CORE_ARTIFACTS = (
    "spring-core",
    "spring-context",
    "spring-webmvc",
    "spring-web",
    "spring-beans",
)

_PROPERTY_KEYS = (
    "spring.version",
    "spring-framework.version",
    "springframework.version",
    "spring.framework.version",
)

_GRADLE_PROPERTY_NAMES = (
    "springVersion",
    "springFrameworkVersion",
    "spring_version",
)


class SpringFrameworkDetector:
    def detect(
        self,
        pom_root: Element | None,
        build_gradle_text: str,
    ) -> str | None:
        if pom_root is not None:
            version = self._from_maven(pom_root)
            if version:
                return version
        if build_gradle_text:
            version = self._from_gradle(build_gradle_text)
            if version:
                return version
        return None

    # -- Maven --------------------------------------------------------------- #

    def _from_maven(self, pom_root: Element) -> str | None:
        properties: dict[str, str] = {}
        properties_block = pom_root.find("properties")
        if properties_block is not None:
            for child in properties_block:
                if child.text:
                    properties[child.tag] = child.text.strip()

        for key in _PROPERTY_KEYS:
            value = properties.get(key)
            if value:
                return value

        for dependency in pom_root.iter("dependency"):
            group = dependency.find("groupId")
            artifact = dependency.find("artifactId")
            if (
                group is not None and group.text == "org.springframework"
                and artifact is not None and artifact.text in _CORE_ARTIFACTS
            ):
                version = dependency.find("version")
                if version is not None and version.text and "$" not in version.text:
                    return version.text.strip()
                if version is not None and version.text:
                    match = re.fullmatch(r"\$\{(.+?)\}", version.text.strip())
                    if match:
                        resolved = properties.get(match.group(1))
                        if resolved:
                            return resolved
        return None

    # -- Gradle -------------------------------------------------------------- #

    def _from_gradle(self, build_text: str) -> str | None:
        for artifact in _CORE_ARTIFACTS:
            match = re.search(
                rf"org\.springframework:{re.escape(artifact)}:([\w.\-]+)",
                build_text,
            )
            if match:
                return match.group(1)

        for name in _GRADLE_PROPERTY_NAMES:
            match = re.search(
                rf"{re.escape(name)}\s*[=:]\s*['\"]([\w.\-]+)['\"]",
                build_text,
            )
            if match:
                return match.group(1)
        return None
