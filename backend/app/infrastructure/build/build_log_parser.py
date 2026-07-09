"""Condenses Maven/Gradle build output into UI/log-friendly lines."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.infrastructure.build.gradle_log_hints import add_gradle_hints

_NOISE = ("Downloading from", "Downloaded from", "Progress (", "Uploading")

# Substrings (matched case-insensitively) that mark a line as failure detail.
# Covers Maven ([ERROR]/BUILD FAILURE) and Gradle, whose real cause lives in the
# "FAILURE:" / "What went wrong" / "Caused by:" block (e.g. AccessDeniedException
# / "Could not move temporary workspace" from AV locking the cache).
_ERROR_TOKENS = (
    "[ERROR]",
    "BUILD FAILURE",
    "BUILD FAILED",
    "COMPILATION ERROR",
    "FAILURE:",
    "WHAT WENT WRONG",
    "CAUSED BY:",
    "COULD NOT ",
    "EXCEPTION",
)


@dataclass(frozen=True)
class ParsedBuildLog:
    lines: list[str] = field(default_factory=list)
    error_lines: list[str] = field(default_factory=list)


def parse_build_output(stdout: str, stderr: str, *, max_lines: int = 300) -> ParsedBuildLog:
    combined = (stdout or "") + ("\n" + stderr if stderr else "")
    lines: list[str] = []
    errors: list[str] = []

    for raw in combined.splitlines():
        line = raw.rstrip()
        if not line.strip() or any(token in line for token in _NOISE):
            continue
        lines.append(line)
        upper = line.upper()
        if any(token in upper for token in _ERROR_TOKENS) or (
            "> TASK :" in upper and "FAILED" in upper
        ):
            errors.append(line.strip())

    if len(lines) > max_lines:
        lines = lines[: max_lines // 2] + ["... (build log truncated) ..."] + lines[-max_lines // 2 :]

    errors = add_gradle_hints(lines, errors)
    return ParsedBuildLog(lines=lines, error_lines=errors[:50])

