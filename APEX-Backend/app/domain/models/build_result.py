"""Result of validating that the migrated project still builds.

Also reused (via ``MavenTestRunner``/``GenerateUnitTestsUseCase``) as the
result shape for compiling/running generated unit tests -- both are "did this
external Maven/Gradle process really succeed" outcomes with the same fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.shared.command_runner import CommandResult

BUILD_STATUS_SUCCESS = "SUCCESS"
BUILD_STATUS_FAILED = "FAILED"
BUILD_STATUS_TIMEOUT = "TIMEOUT"
BUILD_STATUS_SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class BuildResult:
    success: bool
    tool: str  # "maven" | "gradle" | "none"
    skipped: bool = False  # true when validation was disabled or not applicable
    log_lines: list[str] = field(default_factory=list)
    error_lines: list[str] = field(default_factory=list)
    status: str = BUILD_STATUS_SKIPPED
    return_code: int | None = None
    duration_ms: int | None = None
    # Clean, single-line failure reason safe to surface in a report/API
    # response (never a raw stack trace or full log dump).
    safe_summary: str | None = None

    @property
    def status_label(self) -> str:
        if self.skipped:
            return "BUILD SKIPPED"
        return "BUILD SUCCESS" if self.success else "BUILD FAILED"

    @classmethod
    def from_command(
        cls, tool: str, command_result: "CommandResult", parsed: Any, duration_ms: int
    ) -> "BuildResult":
        """Build from a raw ``CommandResult`` + parsed log lines.

        Shared by ``BuildValidator`` (compile-only validation) and
        ``MavenTestRunner`` (compiling/running unit tests) -- both invoke an
        external Maven/Gradle process and need the same success/timeout/
        failure classification from its exit code.
        """
        if command_result.timed_out:
            status = BUILD_STATUS_TIMEOUT
        elif command_result.succeeded:
            status = BUILD_STATUS_SUCCESS
        else:
            status = BUILD_STATUS_FAILED
        safe_summary = None
        if status != BUILD_STATUS_SUCCESS:
            safe_summary = parsed.error_lines[-1] if parsed.error_lines else f"{tool} process failed."
        return cls(
            success=command_result.succeeded,
            tool=tool,
            log_lines=parsed.lines,
            error_lines=parsed.error_lines,
            status=status,
            return_code=command_result.exit_code,
            duration_ms=duration_ms,
            safe_summary=safe_summary,
        )
