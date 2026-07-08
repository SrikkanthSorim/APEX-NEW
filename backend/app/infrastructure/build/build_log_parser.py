"""Condenses Maven/Gradle build output into UI/log-friendly lines."""

from __future__ import annotations

from dataclasses import dataclass, field

_NOISE = ("Downloading from", "Downloaded from", "Progress (", "Uploading")


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
        if (
            "[ERROR]" in upper
            or "BUILD FAILURE" in upper
            or "BUILD FAILED" in upper
            or "COMPILATION ERROR" in upper
            or "> TASK :" in upper and "FAILED" in upper
        ):
            errors.append(line.strip())

    if len(lines) > max_lines:
        lines = lines[: max_lines // 2] + ["... (build log truncated) ..."] + lines[-max_lines // 2 :]

    return ParsedBuildLog(lines=lines, error_lines=errors[:50])
