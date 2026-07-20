"""Pre-flight modernization for legacy Gradle builds before OpenRewrite.

OpenRewrite's current Gradle plugin needs a modern Gradle/JVM runtime. Very
old projects (Gradle 4/5 plus Java 8-era buildscript plugins) can fail before
any recipe runs, so this performs a narrow buildscript lift just far enough for
the rewrite task to evaluate.
"""

from __future__ import annotations

import re
from pathlib import Path


_GRADLE_8_VERSION = "8.14.3"
_SPRING_BOOT_2_TRANSITION_VERSION = "2.7.18"
_SPRING_DEPENDENCY_MANAGEMENT_VERSION = "1.1.7"


class GradlePreflightModernizer:
    """Best-effort, deterministic modernization for old Gradle projects."""

    def modernize(self, project_dir: Path, target_major: int | None) -> list[str]:
        build_file = self._find_build_file(project_dir)
        if build_file is None:
            return []

        changes: list[str] = []
        wrapper_changes = self._modernize_wrapper(project_dir, target_major)
        changes.extend(wrapper_changes)

        text = build_file.read_text(encoding="utf-8", errors="ignore")
        updated = text

        updated = self._modernize_dependency_configurations(updated)
        updated = self._modernize_source_compatibility(updated, target_major)
        updated = self._modernize_spring_boot_buildscript(updated)
        updated = self._modernize_spring_dependency_management_buildscript(updated)
        updated = self._modernize_report_configuration(updated)
        updated = self._disable_legacy_spotbugs(updated)

        if updated != text:
            build_file.write_text(updated, encoding="utf-8")
            changes.append(f"Modernized legacy Gradle build script in {build_file.name} before OpenRewrite.")

        return changes

    @staticmethod
    def _find_build_file(project_dir: Path) -> Path | None:
        for name in ("build.gradle", "build.gradle.kts"):
            candidate = project_dir / name
            if candidate.is_file():
                return candidate
        return None

    def _modernize_wrapper(self, project_dir: Path, target_major: int | None) -> list[str]:
        properties = project_dir / "gradle" / "wrapper" / "gradle-wrapper.properties"
        if not properties.is_file():
            return []

        text = properties.read_text(encoding="utf-8", errors="ignore")
        version = self._wrapper_version(text)
        if version is None:
            return []
        if not self._needs_modern_wrapper(version, target_major):
            return []

        updated = re.sub(
            r"distributionUrl=.*gradle-[^/\\]+-(?:bin|all)\.zip",
            f"distributionUrl=https\\://services.gradle.org/distributions/gradle-{_GRADLE_8_VERSION}-bin.zip",
            text,
            count=1,
        )
        if updated == text:
            return []

        properties.write_text(updated, encoding="utf-8")
        return [
            f"Modernized Gradle wrapper from {version[0]}.{version[1]} to {_GRADLE_8_VERSION} "
            "so the OpenRewrite Gradle plugin can run on Java 17+."
        ]

    @staticmethod
    def _wrapper_version(text: str) -> tuple[int, int] | None:
        match = re.search(r"gradle-(\d+)\.(\d+)(?:[.\-][^/\\]+)?-(?:bin|all)\.zip", text)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    @staticmethod
    def _needs_modern_wrapper(version: tuple[int, int], target_major: int | None) -> bool:
        major, minor = version
        if target_major is not None and target_major >= 17:
            return major < 7 or (major == 7 and minor < 3)
        return major < 6

    @staticmethod
    def _modernize_dependency_configurations(text: str) -> str:
        replacements = {
            "compile": "implementation",
            "runtime": "runtimeOnly",
            "testCompile": "testImplementation",
            "testRuntime": "testRuntimeOnly",
        }
        updated = text
        for old, new in replacements.items():
            updated = re.sub(rf"\b{old}\s*(?=\()", new, updated)
            updated = re.sub(rf"\b{old}\s+(?=[\"'])", f"{new} ", updated)
        return updated

    @staticmethod
    def _modernize_source_compatibility(text: str, target_major: int | None) -> str:
        if target_major is None:
            return text
        updated = re.sub(r"(?m)^\s*sourceCompatibility\s*=\s*[^\r\n]+\r?\n?", "", text)
        updated = re.sub(r"(?m)^\s*targetCompatibility\s*=\s*[^\r\n]+\r?\n?", "", updated)
        updated = re.sub(
            r"(?m)^[ \t]*toolchain\s*\{\r?\n"
            r"[ \t]*languageVersion\s*=\s*JavaLanguageVersion\.of\(\d+\)\r?\n"
            r"[ \t]*\}\r?\n?",
            "",
            updated,
        )
        toolchain_block = (
            "    toolchain {\n"
            f"        languageVersion = JavaLanguageVersion.of({target_major})\n"
            "    }\n"
        )
        if re.search(r"\bjava\s*\{", updated):
            updated = re.sub(
                r"java\s*\{",
                "java {\n" + toolchain_block,
                updated,
                count=1,
            )
        else:
            updated += (
                "\njava {\n"
                f"{toolchain_block}"
                "}\n"
            )
        return updated

    @staticmethod
    def _modernize_spring_boot_buildscript(text: str) -> str:
        return re.sub(
            r"springBootVersion\s*=\s*['\"]2\.[0-6][^'\"]*['\"]",
            f"springBootVersion = '{_SPRING_BOOT_2_TRANSITION_VERSION}'",
            text,
        )

    @staticmethod
    def _modernize_spring_dependency_management_buildscript(text: str) -> str:
        if "io.spring.dependency-management" not in text:
            return text

        coordinate = (
            "io.spring.gradle:dependency-management-plugin:"
            f"{_SPRING_DEPENDENCY_MANAGEMENT_VERSION}"
        )
        updated = re.sub(
            r"io\.spring\.gradle:dependency-management-plugin:[^\"')]+",
            coordinate,
            text,
        )
        if coordinate in updated:
            return updated

        return re.sub(
            r"(?m)^([ \t]*)classpath\((['\"])org\.springframework\.boot:"
            r"spring-boot-gradle-plugin:\$\{springBootVersion\}\2\)\s*$",
            rf"\1classpath(\2org.springframework.boot:spring-boot-gradle-plugin:${{springBootVersion}}\2)"
            "\n"
            rf"\1classpath(\2{coordinate}\2)",
            updated,
            count=1,
        )

    @staticmethod
    def _modernize_report_configuration(text: str) -> str:
        updated = re.sub(
            r"(?m)^(\s*)(xml|csv|html)\.enabled\s+([A-Za-z]+)\s*$",
            r"\1\2.required = \3",
            text,
        )
        updated = re.sub(
            r"(?m)^(\s*)(xml|csv|html)\.enabled\s*=\s*([A-Za-z]+)\s*$",
            r"\1\2.required = \3",
            updated,
        )
        return updated

    @staticmethod
    def _disable_legacy_spotbugs(text: str) -> str:
        updated = re.sub(
            r"(?m)^(\s*)classpath\s+[\"']gradle\.plugin\.com\.github\.spotbugs:spotbugs-gradle-plugin:[^\"']+[\"']\s*$",
            r"\1// Disabled by JavaApex preflight: legacy SpotBugs plugin blocks modern Gradle/OpenRewrite evaluation.",
            text,
        )
        updated = re.sub(
            r"(?m)^(\s*)apply plugin:\s*[\"']com\.github\.spotbugs[\"']\s*$",
            r"\1// Disabled by JavaApex preflight: apply plugin: com.github.spotbugs",
            updated,
        )
        updated = re.sub(
            r"(?ms)^\s*spotbugs\s*\{.*?^\s*\}\s*",
            "",
            updated,
        )
        return updated
