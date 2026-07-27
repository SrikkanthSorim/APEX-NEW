"""Builds the downloadable Unit Test Report HTML (Step 13's "Download Unit
Test Report (HTML)" button). Pure Python string templating -- no template
engine dependency -- built entirely from the persisted, real
``unit-test-report.json``.
"""

from __future__ import annotations

import html
from typing import Any


def render_html_report(job_id: str, unit_test_report: dict[str, Any] | None) -> str:
    if not unit_test_report:
        return _empty_report_html(job_id)

    summary = unit_test_report.get("summary") or {}
    coverage = unit_test_report.get("coverage") or {}
    generated_files = unit_test_report.get("generatedFiles") or []
    failures = unit_test_report.get("failures") or []
    status = unit_test_report.get("status") or "NOT_STARTED"
    generated_at = unit_test_report.get("completedAt") or unit_test_report.get("updatedAt") or ""

    summary_rows = "".join(
        f"<tr><td>{html.escape(label)}</td><td>{html.escape(str(value))}</td></tr>"
        for label, value in (
            ("Total Files in Repo", summary.get("totalSourceFiles", 0)),
            ("Existing Test Files", summary.get("existingTestFiles", 0)),
            ("New Test Files", summary.get("newTestFiles", 0)),
            ("Existing Test Cases", summary.get("existingTestCases", 0)),
            ("Generated Test Cases", summary.get("generatedTestCases", 0)),
            ("Total Test Cases", summary.get("totalTestCases", 0)),
            ("Passed Tests", summary.get("passedTests", 0)),
            ("Failed Tests", summary.get("failedTests", 0)),
            ("Skipped Tests", summary.get("skippedTests", 0)),
            (
                "BL Business Logic Coverage",
                _pct(coverage.get("businessLogicLineCoverage"), coverage.get("businessLogicCoverageReason")),
            ),
            ("JaCoCo Line Coverage", _pct(coverage.get("jacocoLineCoverage"), coverage.get("jacocoCoverageReason"))),
            ("Branch Coverage", _pct(coverage.get("branchCoverage"), None)),
        )
    )

    files_rows = "".join(
        f"<tr><td>{html.escape(str(f.get('className', '')))}</td>"
        f"<td>{html.escape(str(f.get('path', '')))}</td>"
        f"<td>{html.escape(str(f.get('testCount', 0)))}</td>"
        f"<td class=\"status-{html.escape(str(f.get('status', '')).lower())}\">{html.escape(str(f.get('status', '')))}</td></tr>"
        for f in generated_files
    ) or "<tr><td colspan=\"4\">No new test files were generated.</td></tr>"

    failure_rows = "".join(
        f"<tr><td>{html.escape(str(f.get('testClass', '')))}</td>"
        f"<td>{html.escape(str(f.get('testMethod', '')))}</td>"
        f"<td>{html.escape(str(f.get('type', '')))}</td>"
        f"<td>{html.escape(str(f.get('reason', '')))}</td></tr>"
        for f in failures
    ) or "<tr><td colspan=\"4\">No failures recorded.</td></tr>"

    error_summary = unit_test_report.get("errorSummary")
    error_block = (
        f"<p class=\"error\">{html.escape(str(error_summary))}</p>" if error_summary else ""
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Unit Test Report - {html.escape(job_id)}</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; margin: 2rem; color: #1f2937; }}
h1 {{ font-size: 1.4rem; }}
h2 {{ font-size: 1.1rem; margin-top: 2rem; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 0.5rem; }}
td, th {{ border: 1px solid #d1d5db; padding: 6px 10px; text-align: left; font-size: 0.9rem; }}
.status-passed {{ color: #166534; font-weight: 600; }}
.status-failed {{ color: #b91c1c; font-weight: 600; }}
.status-rejected {{ color: #92400e; font-weight: 600; }}
.error {{ color: #b91c1c; }}
.meta {{ color: #6b7280; font-size: 0.85rem; }}
</style></head>
<body>
<h1>Unit Test Report</h1>
<p class="meta">Job ID: {html.escape(job_id)} &middot; Status: {html.escape(status)} &middot; Generated: {html.escape(str(generated_at))}</p>
{error_block}
<h2>Summary</h2>
<table>{summary_rows}</table>
<h2>Generated Test Files</h2>
<table><tr><th>Class</th><th>Path</th><th>Test Count</th><th>Status</th></tr>{files_rows}</table>
<h2>Failures</h2>
<table><tr><th>Test Class</th><th>Test Method</th><th>Type</th><th>Reason</th></tr>{failure_rows}</table>
</body></html>
"""


def _pct(value: Any, reason: str | None) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.1f}%"
    return f"N/A ({reason})" if reason else "N/A"


def _empty_report_html(job_id: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Unit Test Report - {html.escape(job_id)}</title></head>
<body><h1>Unit Test Report</h1>
<p>No unit test analysis has been run yet for job {html.escape(job_id)}.</p>
</body></html>
"""
