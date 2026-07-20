"""Repairs common Maven POM structure problems before migration/build steps."""

from __future__ import annotations

import re
from pathlib import Path

from app.shared import file_utils


class PomSanitizer:
    """Best-effort cleanup for source POMs that Maven cannot parse."""

    _DEPENDENCIES_TAG_PATTERN = re.compile(r"</?dependencies\b[^>]*>", flags=re.IGNORECASE)

    _ANNOTATION_PROCESSOR_PATHS_PATTERN = re.compile(
        r"<annotationProcessorPaths>.*?</annotationProcessorPaths>", flags=re.IGNORECASE | re.DOTALL
    )
    _PATH_ENTRY_PATTERN = re.compile(
        r"(?P<indent>[ \t]*)<path>(?P<body>.*?)</path>", flags=re.IGNORECASE | re.DOTALL
    )
    _GROUP_ARTIFACT_PATTERN = re.compile(
        r"<groupId>\s*(?P<group>[^<]+?)\s*</groupId>\s*<artifactId>\s*(?P<artifact>[^<]+?)\s*</artifactId>",
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Annotation processors whose version is reliably exposed as a property
    # by mainstream parent POMs (e.g. Spring Boot's spring-boot-dependencies
    # BOM defines "lombok.version" even though lombok's own <dependency>
    # entry omits an explicit version). An annotationProcessorPaths <path>
    # left without <version> fails Maven's own dependency resolution
    # ("version can neither be null, empty nor blank") before OpenRewrite's
    # recipe task ever runs, so this has to be repaired ahead of the build.
    _PROCESSOR_VERSION_PROPERTIES = {
        ("org.projectlombok", "lombok"): "${lombok.version}",
        ("org.mapstruct", "mapstruct-processor"): "${org.mapstruct.version}",
    }

    _PARENT_PATTERN = re.compile(r"<parent>(?P<body>.*?)</parent>", flags=re.IGNORECASE | re.DOTALL)
    _DEPENDENCY_MANAGEMENT_DEPS_PATTERN = re.compile(
        r"<dependencyManagement>\s*<dependencies>", flags=re.IGNORECASE
    )
    _TOP_LEVEL_DEPENDENCIES_PATTERN = re.compile(r"(?P<indent>[ \t]*)<dependencies>", flags=re.IGNORECASE)

    # spring-boot-starter-parent 2.0.x manages hibernate-validator 6.0.9.Final
    # -6.0.12.Final. Those releases have a "jdk11+" activation profile in their
    # own POM (HV-1647) that declares org.openjfx:javafx.base:11.0.0-SNAPSHOT
    # -- a nonexistent, typo'd coordinate. Any consumer built with a JDK >= 11
    # (which this pipeline always does for its pre-recipe compile check, since
    # it runs under the migration's target JDK, not the project's original
    # one) inherits that profile and fails dependency resolution before
    # OpenRewrite ever runs. Fixed upstream in 6.0.13.Final (correct
    # "javafx-base" coordinate, provided scope); pinning to the last 6.0.x
    # patch sidesteps the bug without changing behavior for the project.
    _AFFECTED_SPRING_BOOT_PARENT_VERSION_PREFIX = "2.0."
    _HIBERNATE_VALIDATOR_OVERRIDE_VERSION = "6.0.23.Final"

    def sanitize_project(self, project_dir: Path) -> list[str]:
        changes: list[str] = []
        for pom in project_dir.rglob("pom.xml"):
            result = self._sanitize_pom(pom)
            changes.extend(result)
        return changes

    def _sanitize_pom(self, pom: Path) -> list[str]:
        text = file_utils.read_text(pom)
        changes: list[str] = []

        flattened = self._flatten_nested_dependencies(text)
        if flattened != text:
            changes.append(f"Sanitized malformed nested dependencies in {pom.name}")
            text = flattened

        fixed, processor_fixes = self._fix_missing_annotation_processor_versions(text)
        if processor_fixes:
            text = fixed
            for group, artifact in processor_fixes:
                changes.append(
                    f"Added missing annotationProcessorPaths version for {group}:{artifact} in {pom.name}"
                )

        fixed, pinned_hibernate_validator = self._fix_hibernate_validator_javafx_leak(text)
        if pinned_hibernate_validator:
            text = fixed
            changes.append(
                f"Pinned hibernate-validator to {self._HIBERNATE_VALIDATOR_OVERRIDE_VERSION} in {pom.name} "
                "(spring-boot-starter-parent 2.0.x manages a version whose jdk11+ profile pulls in a "
                "nonexistent javafx.base coordinate, breaking dependency resolution on JDK 11+)"
            )

        if changes:
            pom.write_text(text, encoding="utf-8")
        return changes

    def _flatten_nested_dependencies(self, text: str) -> str:
        pieces: list[str] = []
        last_end = 0
        depth = 0

        for match in self._DEPENDENCIES_TAG_PATTERN.finditer(text):
            pieces.append(text[last_end:match.start()])
            tag = match.group(0)
            is_close = tag.lower().startswith("</")

            if is_close:
                if depth <= 1:
                    pieces.append(tag)
                depth = max(depth - 1, 0)
            else:
                if depth == 0:
                    pieces.append(tag)
                depth += 1
            last_end = match.end()

        pieces.append(text[last_end:])
        return "".join(pieces)

    def _fix_missing_annotation_processor_versions(
        self, text: str
    ) -> tuple[str, list[tuple[str, str]]]:
        fixes: list[tuple[str, str]] = []

        def fix_block(block_match: re.Match[str]) -> str:
            return self._PATH_ENTRY_PATTERN.sub(lambda m: self._fix_path_entry(m, fixes), block_match.group(0))

        return self._ANNOTATION_PROCESSOR_PATHS_PATTERN.sub(fix_block, text), fixes

    def _fix_path_entry(self, match: re.Match[str], fixes: list[tuple[str, str]]) -> str:
        indent = match.group("indent")
        body = match.group("body")

        if re.search(r"<version>", body, flags=re.IGNORECASE):
            return match.group(0)

        ga_match = self._GROUP_ARTIFACT_PATTERN.search(body)
        if not ga_match:
            return match.group(0)

        group = ga_match.group("group").strip()
        artifact = ga_match.group("artifact").strip()
        version = self._PROCESSOR_VERSION_PROPERTIES.get((group, artifact))
        if not version:
            return match.group(0)

        indent_match = re.search(r"(?m)^([ \t]*)<groupId>", body)
        child_indent = indent_match.group(1) if indent_match else indent + "\t"
        line_ending = "\r\n" if "\r\n" in body else "\n"

        artifact_close = "</artifactId>"
        insert_at = body.index(artifact_close) + len(artifact_close)
        new_body = (
            body[:insert_at]
            + f"{line_ending}{child_indent}<version>{version}</version>"
            + body[insert_at:]
        )

        fixes.append((group, artifact))
        return f"{indent}<path>{new_body}</path>"

    def _fix_hibernate_validator_javafx_leak(self, text: str) -> tuple[str, bool]:
        parent_match = self._PARENT_PATTERN.search(text)
        if not parent_match:
            return text, False
        parent_body = parent_match.group("body")
        if "spring-boot-starter-parent" not in parent_body:
            return text, False

        version_match = re.search(r"<version>\s*([^<]+?)\s*</version>", parent_body, flags=re.IGNORECASE)
        if not version_match or not version_match.group(1).startswith(
            self._AFFECTED_SPRING_BOOT_PARENT_VERSION_PREFIX
        ):
            return text, False

        if re.search(r"<artifactId>\s*hibernate-validator\s*</artifactId>", text, flags=re.IGNORECASE):
            # Already explicitly managed/declared -- respect the existing choice.
            return text, False

        dependency_entry = (
            "\t\t\t<dependency>\n"
            "\t\t\t\t<groupId>org.hibernate.validator</groupId>\n"
            "\t\t\t\t<artifactId>hibernate-validator</artifactId>\n"
            f"\t\t\t\t<version>{self._HIBERNATE_VALIDATOR_OVERRIDE_VERSION}</version>\n"
            "\t\t\t</dependency>\n"
        )

        dep_mgmt_match = self._DEPENDENCY_MANAGEMENT_DEPS_PATTERN.search(text)
        if dep_mgmt_match:
            insert_at = dep_mgmt_match.end()
            new_text = text[:insert_at] + "\n" + dependency_entry.rstrip("\n") + text[insert_at:]
            return new_text, True

        deps_match = self._TOP_LEVEL_DEPENDENCIES_PATTERN.search(text)
        if not deps_match:
            return text, False

        indent = deps_match.group("indent")
        block = (
            f"{indent}<dependencyManagement>\n"
            f"{indent}\t<dependencies>\n"
            f"{dependency_entry}"
            f"{indent}\t</dependencies>\n"
            f"{indent}</dependencyManagement>\n\n"
        )
        insert_at = deps_match.start()
        new_text = text[:insert_at] + block + text[insert_at:]
        return new_text, True
