"""Lightweight fallback migration when OpenRewrite can't run.

Best-effort: bumps the Java version declared in the build file so the published
repo at least targets the requested version. Text-based, no build tool required.
Only used if the OpenRewrite run fails; recorded in the migration log.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.shared import file_utils


class InternalRewriteRunner:
    def bump_java_version(self, project_dir: Path, build_tool: str, target_major: int) -> list[str]:
        """Update the build file's Java version to ``target_major``.

        Returns a list of human-readable log lines describing what changed.
        """
        if build_tool == "MAVEN":
            return self._bump_maven(project_dir / "pom.xml", target_major)
        if build_tool == "GRADLE":
            for name in ("build.gradle", "build.gradle.kts"):
                path = project_dir / name
                if path.is_file():
                    return self._bump_gradle(path, target_major)
        return []

    # -- Maven --------------------------------------------------------------- #

    @staticmethod
    def _bump_maven(pom: Path, target: int) -> list[str]:
        if not pom.is_file():
            return []
        text = file_utils.read_text(pom)
        original = text
        for prop in (
            "maven.compiler.release",
            "maven.compiler.source",
            "maven.compiler.target",
            "java.version",
        ):
            text = re.sub(
                rf"(<{prop}>)\s*[\w.]+\s*(</{prop}>)",
                rf"\g<1>{target}\g<2>",
                text,
            )
        # <source>/<target>/<release> inside the compiler plugin config.
        for tag in ("release", "source", "target"):
            text = re.sub(
                rf"(<{tag}>)\s*1?\.?\d+\s*(</{tag}>)",
                rf"\g<1>{target}\g<2>",
                text,
            )
        if text != original:
            pom.write_text(text, encoding="utf-8")
            return [f"Fallback: set Java version to {target} in pom.xml"]
        return []

    # -- Gradle -------------------------------------------------------------- #

    @staticmethod
    def _bump_gradle(build_file: Path, target: int) -> list[str]:
        text = file_utils.read_text(build_file)
        original = text
        text = re.sub(
            r"((?:source|target)Compatibility\s*=?\s*)['\"]?[\w.]+['\"]?",
            rf"\g<1>'{target}'",
            text,
        )
        text = re.sub(r"JavaVersion\.VERSION_\d+(?:_\d+)?", f"JavaVersion.VERSION_{target}", text)
        text = re.sub(r"JavaLanguageVersion\.of\(\d+\)", f"JavaLanguageVersion.of({target})", text)
        if text != original:
            build_file.write_text(text, encoding="utf-8")
            return [f"Fallback: set Java version to {target} in {build_file.name}"]
        return []
