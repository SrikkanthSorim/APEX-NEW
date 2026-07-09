"""Ensures a Gradle project's wrapper can run on the target JDK.

Old Gradle wrappers can't run on newer JDKs (Java 21 needs Gradle 8.5+), so a
repo pinned to e.g. 7.6.1 fails to even launch under JDK 21 -- both OpenRewrite's
``rewriteRun`` and the post-migration build validation die with
``Unsupported class file major version 65``.

This bumps the wrapper's ``distributionUrl`` to a Gradle version compatible with
the target Java *before* any Gradle is invoked. It's a pure text edit on
``gradle-wrapper.properties`` (no Gradle needed -- essential, because the old
wrapper can't launch on the new JDK to upgrade itself). Upgrade only: a wrapper
already newer than the recommended version is left untouched.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.shared import file_utils

# Highest applicable (target_major, recommended_gradle_version), ordered high->low.
# Recommended versions are known-good for running the build on that target JDK:
#   Java 21 -> Gradle 8.5+   Java 17 -> Gradle 7.3+   Java 11 -> Gradle 5+
_TARGET_GRADLE = [
    (21, "8.9"),
    (17, "8.9"),
    (11, "7.6.4"),
]

_WRAPPER_REL_PATH = Path("gradle") / "wrapper" / "gradle-wrapper.properties"
_DIST_URL_RE = re.compile(r"(gradle-)([0-9]+(?:\.[0-9]+)*)(-(?:bin|all)\.zip)")


def _recommended_gradle(target_major: int) -> str | None:
    for threshold, version in _TARGET_GRADLE:
        if target_major >= threshold:
            return version
    return None


def _parse_version(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in text.split(".") if p.isdigit())


class GradleWrapperUpgrader:
    def ensure_compatible(self, project_dir: Path, target_major: int | None) -> list[str]:
        """Bump the wrapper to a Gradle version that runs on ``target_major``.

        Returns human-readable log lines describing any change (empty if none).
        """
        if target_major is None:
            return []
        recommended = _recommended_gradle(target_major)
        if recommended is None:
            return []

        props = project_dir / _WRAPPER_REL_PATH
        if not props.is_file():
            return []

        text = file_utils.read_text(props)
        match = _DIST_URL_RE.search(text)
        if not match:
            return []

        current = match.group(2)
        if _parse_version(current) >= _parse_version(recommended):
            return []  # already new enough; never downgrade

        new_text = _DIST_URL_RE.sub(rf"\g<1>{recommended}\g<3>", text, count=1)
        if new_text == text:
            return []
        props.write_text(new_text, encoding="utf-8")
        return [
            f"Upgraded Gradle wrapper {current} -> {recommended} "
            f"(required to build on Java {target_major})"
        ]
