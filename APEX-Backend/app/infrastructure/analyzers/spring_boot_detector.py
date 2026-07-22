"""Detects Spring Boot from real project files: the Maven parent/BOM, the
Maven or Gradle plugin, and version-bearing ``spring-boot-starter-*`` /
``org.springframework.boot`` coordinates.

``detect`` returns the version string when one can be resolved (parent,
property, explicit dependency/plugin version, or BOM import), otherwise
``None``. ``has_signal`` is a broader, version-independent boolean: it also
catches projects that declare the Spring Boot Maven/Gradle plugin or import
the ``spring-boot-dependencies`` BOM without an explicit, directly-readable
version (e.g. inherited from a custom parent).
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

    def has_signal(
        self,
        pom_root: Element | None,
        build_gradle_text: str,
    ) -> bool:
        """True when a Spring Boot indicator is present, even without a
        resolvable version number (e.g. plugin declared without a version,
        or a BOM import managed elsewhere).
        """
        if self.detect(pom_root, build_gradle_text):
            return True
        if pom_root is not None and self._maven_signal(pom_root):
            return True
        if build_gradle_text and self._gradle_signal(build_gradle_text):
            return True
        return False

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

        # <dependencyManagement> import of the spring-boot-dependencies BOM.
        dependency_management = pom_root.find("dependencyManagement")
        if dependency_management is not None:
            deps_block = dependency_management.find("dependencies")
            if deps_block is not None:
                for dependency in deps_block.findall("dependency"):
                    group = dependency.find("groupId")
                    artifact = dependency.find("artifactId")
                    dep_type = dependency.find("type")
                    scope = dependency.find("scope")
                    if (
                        group is not None and group.text == "org.springframework.boot"
                        and artifact is not None and artifact.text == "spring-boot-dependencies"
                        and dep_type is not None and dep_type.text == "pom"
                        and scope is not None and scope.text == "import"
                    ):
                        version = dependency.find("version")
                        if version is not None and version.text and "$" not in version.text:
                            return version.text.strip()
        return None

    def _maven_signal(self, pom_root: Element) -> bool:
        """Presence-only checks: BOM import or plugin declared, regardless of
        whether a version could be resolved (e.g. version inherited from a
        custom parent, so no literal version text is present in this pom).
        """
        for plugin in pom_root.iter("plugin"):
            artifact = plugin.find("artifactId")
            if artifact is not None and artifact.text == "spring-boot-maven-plugin":
                return True

        dependency_management = pom_root.find("dependencyManagement")
        if dependency_management is not None:
            deps_block = dependency_management.find("dependencies")
            if deps_block is not None:
                for dependency in deps_block.findall("dependency"):
                    group = dependency.find("groupId")
                    artifact = dependency.find("artifactId")
                    if (
                        group is not None and group.text == "org.springframework.boot"
                        and artifact is not None and artifact.text == "spring-boot-dependencies"
                    ):
                        return True
        return False

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
        # platform("org.springframework.boot:spring-boot-dependencies:3.2.5")
        match = re.search(
            r"spring-boot-dependencies:([\w.\-]+)",
            build_text,
        )
        if match:
            return match.group(1)
        return None

    def _gradle_signal(self, build_text: str) -> bool:
        # id 'org.springframework.boot' (no version -- managed by a parent/platform elsewhere)
        if re.search(r"id\s*[('\"]+org\.springframework\.boot['\")]+", build_text):
            return True
        if "spring-boot-gradle-plugin" in build_text:
            return True
        if "spring-boot-dependencies" in build_text:
            return True
        return False
