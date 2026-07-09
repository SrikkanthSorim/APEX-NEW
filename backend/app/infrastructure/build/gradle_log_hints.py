"""Human-readable hints for known Gradle environment failures."""

from __future__ import annotations

SOPHOS_GRADLE_LOCK_HINT = (
    "SOPHOS/antivirus is blocking Gradle: Gradle could not move a "
    "temporary workspace because files in %USERPROFILE%\\.gradle are locked. "
    "Add a Sophos scanning exclusion for %USERPROFILE%\\.gradle and rerun the migration."
)


def detect_gradle_antivirus_lock(lines: list[str]) -> str | None:
    """Return a migration-log hint for the Gradle cache AccessDenied signature."""
    combined = "\n".join(lines).upper()
    if (
        "COULD NOT MOVE TEMPORARY WORKSPACE" in combined
        and ("ACCESSDENIEDEXCEPTION" in combined or "ACCESS IS DENIED" in combined)
    ):
        return SOPHOS_GRADLE_LOCK_HINT
    return None


def add_gradle_hints(log_lines: list[str], error_lines: list[str]) -> list[str]:
    """Prepend known Gradle hints to error lines so they are prominent in the UI."""
    hint = detect_gradle_antivirus_lock(log_lines + error_lines)
    if hint and hint not in error_lines:
        return [hint] + error_lines
    return error_lines
