"""Pre-flight repair for Gradle build scripts that fail to *evaluate*.

When Gradle crashes while evaluating a project's own ``build.gradle`` --
before OpenRewrite's recipe task ever runs -- no recipe selection can help;
recipes only run once evaluation succeeds. This looks *only* at coordinates
the project itself already declared (``classpath "group:artifact:version"``
in the ``buildscript`` block, or ``id 'x' version 'y'`` in the ``plugins``
block), cross-references them against the crash's own stack trace to find
the one implicated, and -- only if that *same* coordinate has a newer
release available -- bumps just that version string. The "newer release" is
always resolved live from the real Maven Central / Gradle Plugin Portal
metadata for that exact artifact; no coordinate or version is ever invented
or guessed at, and nothing is changed if no newer release exists under the
same coordinate (that signals a manual fix is genuinely required, e.g. the
project needs a different, newer-generation plugin coordinate entirely).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import httpx

_CLASSPATH_PATTERN = re.compile(
    r"classpath\s*[( ]?\s*[\"']([\w.\-]+):([\w.\-]+):([\w.\-+]+)[\"']"
)
_PLUGIN_DSL_PATTERN = re.compile(
    r"id\s*[( ]?\s*[\"']([\w.\-]+)[\"']\s*version\s*[\"']([\w.\-+]+)[\"']"
)
# Dotted, lowercase-leading identifiers with >=3 segments (e.g.
# "com.github.spotbugs.SpotBugsTask") -- how Java stack traces / class-not-
# found errors spell out fully qualified class names.
_QUALIFIED_NAME_PATTERN = re.compile(r"\b((?:[a-z][\w]*\.){2,}[A-Za-z][\w]*)\b")

_METADATA_URL_TEMPLATES = (
    "https://repo.maven.apache.org/maven2/{path}/maven-metadata.xml",
    "https://plugins.gradle.org/m2/{path}/maven-metadata.xml",
)
_HTTP_TIMEOUT = 10.0


@dataclass(frozen=True)
class BuildscriptRepair:
    coordinate: str
    old_version: str
    new_version: str

    def to_dict(self) -> dict[str, str]:
        return {"coordinate": self.coordinate, "oldVersion": self.old_version, "newVersion": self.new_version}


class GradleBuildscriptRepair:
    """Best-effort, same-coordinate-only repair for a Gradle evaluation crash."""

    def repair(self, project_dir: Path, error_text: str) -> tuple[list[str], BuildscriptRepair | None]:
        build_file = self._find_build_file(project_dir)
        if build_file is None:
            return [], None

        text = build_file.read_text(encoding="utf-8", errors="ignore")
        implicated = self._find_implicated_coordinate(text, error_text)
        if implicated is None:
            return [], None
        group, artifact, current_version, is_plugin_dsl = implicated

        latest = self._resolve_latest_release(group, artifact)
        if not latest or latest == current_version:
            return [], None

        new_text = self._bump_version(text, group, artifact, current_version, latest, is_plugin_dsl)
        if new_text == text:
            return [], None

        build_file.write_text(new_text, encoding="utf-8")
        coordinate = group if is_plugin_dsl else f"{group}:{artifact}"
        return (
            [
                f"Pre-flight repair: build evaluation crashed referencing "
                f"{group}.*; bumped declared {'plugin' if is_plugin_dsl else 'classpath dependency'} "
                f"{coordinate} from {current_version} to its current release "
                f"{latest} (resolved live from Maven Central / Gradle Plugin "
                f"Portal) and retrying."
            ],
            BuildscriptRepair(coordinate, current_version, latest),
        )

    # -- detection ------------------------------------------------------------ #

    @staticmethod
    def _find_build_file(project_dir: Path) -> Path | None:
        for name in ("build.gradle", "build.gradle.kts"):
            candidate = project_dir / name
            if candidate.is_file():
                return candidate
        return None

    def _find_implicated_coordinate(
        self, build_text: str, error_text: str
    ) -> tuple[str, str, str, bool] | None:
        mentioned = set(_QUALIFIED_NAME_PATTERN.findall(error_text))
        if not mentioned:
            return None

        candidates: list[tuple[str, str, str, bool]] = [
            (match.group(1), match.group(2), match.group(3), False)
            for match in _CLASSPATH_PATTERN.finditer(build_text)
        ] + [
            (match.group(1), match.group(1), match.group(2), True)
            for match in _PLUGIN_DSL_PATTERN.finditer(build_text)
        ]

        for group, artifact, version, is_plugin_dsl in candidates:
            # "gradle.plugin.<id>" is the standard prefix Gradle Plugin Portal
            # publishes legacy buildscript-classpath coordinates under; strip
            # it so it lines up with the plain package the crash references.
            lookup_group = group.removeprefix("gradle.plugin.")
            if any(name == lookup_group or name.startswith(lookup_group + ".") for name in mentioned):
                return group, artifact, version, is_plugin_dsl
        return None

    # -- resolution ------------------------------------------------------------ #

    @staticmethod
    def _resolve_latest_release(group: str, artifact: str) -> str | None:
        path = f"{group.replace('.', '/')}/{artifact}"
        for template in _METADATA_URL_TEMPLATES:
            url = template.format(path=path)
            try:
                response = httpx.get(url, timeout=_HTTP_TIMEOUT, follow_redirects=True)
            except httpx.HTTPError:
                continue
            if response.status_code != 200:
                continue
            match = re.search(r"<release>([^<]+)</release>", response.text)
            if match:
                return match.group(1).strip()
        return None

    # -- rewrite ------------------------------------------------------------ #

    @staticmethod
    def _bump_version(
        text: str,
        group: str,
        artifact: str,
        old_version: str,
        new_version: str,
        is_plugin_dsl: bool,
    ) -> str:
        if is_plugin_dsl:
            pattern = re.compile(
                rf"(id\s*[( ]?\s*[\"']{re.escape(group)}[\"']\s*version\s*[\"']){re.escape(old_version)}([\"'])"
            )
        else:
            pattern = re.compile(
                rf"(classpath\s*[( ]?\s*[\"']{re.escape(group)}:{re.escape(artifact)}:){re.escape(old_version)}([\"'])"
            )
        return pattern.sub(rf"\g<1>{new_version}\g<2>", text, count=1)
