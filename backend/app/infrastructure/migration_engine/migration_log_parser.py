"""Condenses Maven/Gradle OpenRewrite output into UI-friendly log lines."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.infrastructure.build.gradle_log_hints import add_gradle_hints

# Substrings that mark a line as noise not worth showing in the UI.
_NOISE = (
    "Downloading from",
    "Downloaded from",
    "Progress (",
    "Uploading",
)

_ERROR_TOKENS = (
    "[ERROR]",
    "BUILD FAILURE",
    "BUILD FAILED",
    "FAILURE:",
    "WHAT WENT WRONG",
    "CAUSED BY:",
    "COULD NOT ",
    "EXCEPTION",
    "FAILED",
)


@dataclass(frozen=True)
class ParsedMigrationLog:
    lines: list[str] = field(default_factory=list)
    error_lines: list[str] = field(default_factory=list)


def parse_rewrite_output(stdout: str, stderr: str, *, max_lines: int = 400) -> ParsedMigrationLog:
    """Extract a condensed set of log lines + error lines from tool output."""
    combined = (stdout or "") + ("\n" + stderr if stderr else "")
    lines: list[str] = []
    errors: list[str] = []

    for raw in combined.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if any(token in line for token in _NOISE):
            continue
        lines.append(line)
        upper = line.upper()
        if any(token in upper for token in _ERROR_TOKENS):
            errors.append(line.strip())

    if len(lines) > max_lines:
        # Keep the head and tail - the tail usually holds the outcome.
        head = lines[: max_lines // 2]
        tail = lines[-max_lines // 2 :]
        lines = head + ["... (log truncated) ..."] + tail

    errors = add_gradle_hints(lines, errors)
    return ParsedMigrationLog(lines=lines, error_lines=errors[:50])

