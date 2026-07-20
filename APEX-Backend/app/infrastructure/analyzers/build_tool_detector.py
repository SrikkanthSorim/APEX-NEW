"""Detects the project's build tool from root build files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MAVEN = "MAVEN"
GRADLE = "GRADLE"
UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class BuildToolResult:
    build_tool: str  # MAVEN | GRADLE | UNSUPPORTED
    primary_build_tool: str | None
    has_pom_xml: bool
    has_build_gradle: bool
    has_build_gradle_kts: bool
    warning: str | None = None

    @property
    def is_supported(self) -> bool:
        return self.build_tool in (MAVEN, GRADLE)


class BuildToolDetector:
    def detect(self, root: Path) -> BuildToolResult:
        has_pom = (root / "pom.xml").is_file()
        has_gradle = (root / "build.gradle").is_file()
        has_gradle_kts = (root / "build.gradle.kts").is_file()
        has_any_gradle = has_gradle or has_gradle_kts

        if has_pom and has_any_gradle:
            # Both present: Maven is treated as primary; surface a warning.
            return BuildToolResult(
                build_tool=MAVEN,
                primary_build_tool=MAVEN,
                has_pom_xml=has_pom,
                has_build_gradle=has_gradle,
                has_build_gradle_kts=has_gradle_kts,
                warning=(
                    "Both Maven and Gradle build files were found. "
                    "Maven has been selected as the primary build tool."
                ),
            )

        if has_pom:
            return BuildToolResult(MAVEN, MAVEN, has_pom, has_gradle, has_gradle_kts)

        if has_any_gradle:
            return BuildToolResult(GRADLE, GRADLE, has_pom, has_gradle, has_gradle_kts)

        return BuildToolResult(UNSUPPORTED, None, has_pom, has_gradle, has_gradle_kts)
