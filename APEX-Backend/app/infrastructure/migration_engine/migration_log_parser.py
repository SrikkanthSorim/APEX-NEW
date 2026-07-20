"""Condenses Maven/Gradle OpenRewrite output into UI-friendly log lines."""

from __future__ import annotations

from dataclasses import dataclass, field

# Substrings that mark a line as noise not worth showing in the UI.
_NOISE = (
    "Downloading from",
    "Downloaded from",
    "Progress (",
    "Uploading",
)


# Printed by the Maven/Gradle OpenRewrite plugin once it actually starts
# applying recipes. Its absence on a failed run means the build tool failed
# while evaluating/compiling the project itself (a project-level build
# configuration or plugin incompatibility) -- before any recipe ran, so no
# recipe selection could have prevented or fixed it.
_RECIPE_EXECUTION_MARKERS = ("using active recipe", ":rewriterun")


@dataclass(frozen=True)
class ParsedMigrationLog:
    lines: list[str] = field(default_factory=list)
    error_lines: list[str] = field(default_factory=list)
    reached_recipe_execution: bool = False


def parse_rewrite_output(stdout: str, stderr: str, *, max_lines: int = 400) -> ParsedMigrationLog:
    """Extract a condensed set of log lines + error lines from tool output."""
    combined = (stdout or "") + ("\n" + stderr if stderr else "")
    lines: list[str] = []
    errors: list[str] = []
    reached_recipe_execution = False

    for raw in combined.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if any(token in line for token in _NOISE):
            continue
        lines.append(line)
        lowered = line.lower()
        if any(marker in lowered for marker in _RECIPE_EXECUTION_MARKERS):
            reached_recipe_execution = True
        upper = line.upper()
        if "[ERROR]" in upper or "BUILD FAILURE" in upper or "FAILED" in upper:
            errors.append(line.strip())

    if len(lines) > max_lines:
        # Keep the head and tail — the tail usually holds the outcome.
        head = lines[: max_lines // 2]
        tail = lines[-max_lines // 2 :]
        lines = head + ["... (log truncated) ..."] + tail

    return ParsedMigrationLog(
        lines=lines, error_lines=errors[:50], reached_recipe_execution=reached_recipe_execution
    )
