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
        if "[ERROR]" in upper or "BUILD FAILURE" in upper or "FAILED" in upper:
            errors.append(line.strip())

    if len(lines) > max_lines:
        # Keep the head and tail — the tail usually holds the outcome.
        head = lines[: max_lines // 2]
        tail = lines[-max_lines // 2 :]
        lines = head + ["... (log truncated) ..."] + tail

    return ParsedMigrationLog(lines=lines, error_lines=errors[:50])
