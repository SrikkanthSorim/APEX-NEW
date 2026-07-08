"""Result of validating that the migrated project still builds."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BuildResult:
    success: bool
    tool: str  # "maven" | "gradle" | "none"
    skipped: bool = False  # true when validation was disabled or not applicable
    log_lines: list[str] = field(default_factory=list)
    error_lines: list[str] = field(default_factory=list)

    @property
    def status_label(self) -> str:
        if self.skipped:
            return "BUILD SKIPPED"
        return "BUILD SUCCESS" if self.success else "BUILD FAILED"
