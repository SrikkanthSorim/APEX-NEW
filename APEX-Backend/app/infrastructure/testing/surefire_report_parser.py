"""Parses the JUnit XML test reports Maven Surefire and Gradle's ``Test`` task
both produce (same schema, different on-disk location -- see
``build_tool_paths``) into real pass/fail/skip counts and per-testcase failure
details (Step 7: "Parse actual test information" -- never determine success by
scanning stdout for "BUILD SUCCESS").
"""

from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import Element, ParseError, fromstring

from app.domain.models.unit_test_report import TestExecutionSummary, TestFailureEntry
from app.infrastructure.testing.build_tool_paths import find_test_results_dir


def parse_surefire_reports(project_dir: Path, build_tool: str = "MAVEN") -> TestExecutionSummary:
    """Aggregate every ``TEST-*.xml`` file under the build tool's test-results directory."""
    reports_dir = find_test_results_dir(project_dir, build_tool)
    xml_files = sorted(reports_dir.glob("TEST-*.xml")) if reports_dir.is_dir() else []
    if not xml_files:
        return TestExecutionSummary(available=False, reason="No test reports were found.")
    return _combine(_parse_file(f) for f in xml_files)


def parse_surefire_report_for_class(
    project_dir: Path, fully_qualified_class_name: str, build_tool: str = "MAVEN"
) -> TestExecutionSummary:
    """Parse the single JUnit XML report for one test class (used to gate
    accepting a just-generated test: the file's mere existence proves the
    class compiled -- neither Surefire nor Gradle's ``Test`` task ever writes
    a report for a class that failed to compile).
    """
    xml_file = find_test_results_dir(project_dir, build_tool) / f"TEST-{fully_qualified_class_name}.xml"
    if not xml_file.is_file():
        return TestExecutionSummary(available=False, reason="No test report was produced for this class (did not compile).")
    return _parse_file(xml_file)


def _combine(summaries) -> TestExecutionSummary:
    total = passed = failed = errors = skipped = 0
    duration = 0.0
    failures: list[TestFailureEntry] = []
    any_available = False
    for summary in summaries:
        if not summary.available:
            continue
        any_available = True
        total += summary.total
        failed += summary.failed
        errors += summary.errors
        skipped += summary.skipped
        duration += summary.duration_seconds
        failures.extend(summary.failures)
    passed = total - failed - errors - skipped
    if not any_available:
        return TestExecutionSummary(available=False, reason="No Surefire test reports were found.")
    return TestExecutionSummary(
        available=True, total=total, passed=max(passed, 0), failed=failed, skipped=skipped,
        errors=errors, duration_seconds=round(duration, 3), failures=failures,
    )


def _parse_file(xml_file: Path) -> TestExecutionSummary:
    try:
        root = fromstring(xml_file.read_text(encoding="utf-8", errors="ignore"))
    except (ParseError, OSError) as exc:
        return TestExecutionSummary(available=False, reason=f"Could not parse {xml_file.name}: {exc}")

    classname_default = root.get("name", xml_file.stem.removeprefix("TEST-"))
    total = failed = errors = skipped = 0
    duration = 0.0
    failures: list[TestFailureEntry] = []

    for testcase in root.findall("testcase"):
        total += 1
        duration += _safe_float(testcase.get("time"))
        method = testcase.get("name", "")
        classname = testcase.get("classname", classname_default)

        failure = testcase.find("failure")
        error = testcase.find("error")
        skip = testcase.find("skipped")
        if failure is not None:
            failed += 1
            failures.append(TestFailureEntry(
                test_class=classname, test_method=method, failure_type="FAILURE", reason=_safe_reason(failure),
            ))
        elif error is not None:
            errors += 1
            failures.append(TestFailureEntry(
                test_class=classname, test_method=method, failure_type="ERROR", reason=_safe_reason(error),
            ))
        elif skip is not None:
            skipped += 1

    passed = max(total - failed - errors - skipped, 0)
    return TestExecutionSummary(
        available=True, total=total, passed=passed, failed=failed, skipped=skipped,
        errors=errors, duration_seconds=round(duration, 3), failures=failures,
    )


def _safe_float(value: str | None) -> float:
    try:
        return float(value) if value else 0.0
    except ValueError:
        return 0.0


def _safe_reason(element: Element) -> str:
    message = (element.get("message") or "").strip()
    if message:
        return message.splitlines()[0][:500]
    text = (element.text or "").strip()
    return text.splitlines()[0][:500] if text else "No failure message reported."
