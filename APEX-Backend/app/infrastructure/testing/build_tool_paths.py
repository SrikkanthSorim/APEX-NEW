"""Maven vs Gradle output-path differences for the unit-test pipeline.

Both tools produce the same JUnit XML report schema (Surefire and Gradle's
``Test`` task alike) and both can produce a JaCoCo XML report -- only the
on-disk locations differ. Centralizing that here keeps
``surefire_report_parser``/``jacoco_report_parser``/the use cases build-tool
agnostic everywhere else.
"""

from __future__ import annotations

from pathlib import Path

_GRADLE = "GRADLE"


def find_test_results_dir(project_dir: Path, build_tool: str) -> Path:
    """Directory containing ``TEST-*.xml`` JUnit reports."""
    if (build_tool or "").upper() == _GRADLE:
        return project_dir / "build" / "test-results" / "test"
    return project_dir / "target" / "surefire-reports"


def jacoco_report_path(project_dir: Path, build_tool: str) -> Path:
    """Path to the JaCoCo XML report (never the HTML report)."""
    if (build_tool or "").upper() == _GRADLE:
        return project_dir / "build" / "reports" / "jacoco" / "test" / "jacocoTestReport.xml"
    return project_dir / "target" / "site" / "jacoco" / "jacoco.xml"


def stale_report_dirs(project_dir: Path, build_tool: str) -> tuple[Path, Path]:
    """``(find_test_results_dir, jacoco_report_root)`` to delete before a fresh run
    so a report can only ever reflect the run that just happened."""
    if (build_tool or "").upper() == _GRADLE:
        return (
            project_dir / "build" / "test-results" / "test",
            project_dir / "build" / "reports" / "jacoco",
        )
    return (
        project_dir / "target" / "surefire-reports",
        project_dir / "target" / "site" / "jacoco",
    )
