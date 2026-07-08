"""Detects the Spring Boot version, if the project uses Spring Boot.

Returns the version string when found, otherwise ``None``.
"""

from __future__ import annotations

import re
from xml.etree.ElementTree import Element


class SpringBootDetector:
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
        # <parent> spring-boot-starter-parent
        parent = pom_root.find("parent")
        if parent is not None:
            artifact = parent.find("artifactId")
            if artifact is not None and artifact.text == "spring-boot-starter-parent":
                version = parent.find("version")
                if version is not None and version.text:
                    return version.text.strip()

        # <properties>spring-boot.version</properties>
        properties = pom_root.find("properties")
        if properties is not None:
            for key in ("spring-boot.version", "spring.boot.version"):
                node = properties.find(key)
                if node is not None and node.text:
                    return node.text.strip()

        # A spring-boot dependency / plugin with an explicit version.
        for dependency in pom_root.iter("dependency"):
            group = dependency.find("groupId")
            if group is not None and group.text == "org.springframework.boot":
                version = dependency.find("version")
                if version is not None and version.text and "$" not in version.text:
                    return version.text.strip()

        for plugin in pom_root.iter("plugin"):
            artifact = plugin.find("artifactId")
            if artifact is not None and artifact.text == "spring-boot-maven-plugin":
                version = plugin.find("version")
                if version is not None and version.text and "$" not in version.text:
                    return version.text.strip()
        return None

    # -- Gradle -------------------------------------------------------------- #

    def _from_gradle(self, build_text: str) -> str | None:
        # id 'org.springframework.boot' version '2.7.18'
        match = re.search(
            r"id\s*[('\"]+org\.springframework\.boot['\")]+\s*version\s*['\"]([\w.\-]+)['\"]",
            build_text,
        )
        if match:
            return match.group(1)
        # classpath "org.springframework.boot:spring-boot-gradle-plugin:2.7.18"
        match = re.search(
            r"spring-boot-gradle-plugin:([\w.\-]+)",
            build_text,
        )
        if match:
            return match.group(1)
        return None
