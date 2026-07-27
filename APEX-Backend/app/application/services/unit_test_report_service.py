"""Shapes the persisted ``unit-test-report.json`` into exactly the fields the
frontend's Result page already expects (see ``report_service.py``'s
``_ZERO_ANALYSIS`` overlay and ``APEX-Frontend/src/features/result/services/
resultService.ts``'s ``MigrationResult.test_pipeline``). Every value here
comes from the real persisted report -- nothing is fabricated.
"""

from __future__ import annotations

from typing import Any

_STATUS_MESSAGES = {
    "NOT_STARTED": "Unit test analysis has not started yet.",
    "TEST_ANALYSIS_COMPLETED": "Existing tests detected and analyzed.",
    "NO_TESTS_FOUND": "No existing unit tests were found in this repository.",
    "TEST_GENERATION_IN_PROGRESS": "Generating missing unit tests...",
    "TEST_GENERATED": "Unit tests generated and validated.",
    "TEST_COMPILATION_FAILED": "One or more generated tests failed to compile after repair attempts.",
    "TEST_EXECUTION_PASSED": "All unit tests passed.",
    "TEST_EXECUTION_FAILED": "One or more unit tests failed.",
    "TEST_EXECUTION_TIMEOUT": "Unit test execution timed out.",
    "TEST_NOT_EXECUTED": "Unit tests were not executed.",
    "REPORT_GENERATED": "Unit test report generated.",
    "COMPLETED": "All unit tests passed successfully.",
    "COMPLETED_WITH_ISSUES": "Unit tests completed with some failures.",
    "FAILED": "Unit test analysis/generation failed.",
}


def build_report_overlay(unit_test_report: dict[str, Any] | None) -> dict[str, Any]:
    """Return the overlay fields merged into ``report_service.build_summary``/
    ``build_result`` on top of the zeroed defaults -- empty dict when no
    unit-test report has been persisted yet for the job (the UI then keeps
    showing 0/N/A, honestly, rather than a fabricated number).
    """
    if not unit_test_report:
        return {}

    status = unit_test_report.get("status") or "NOT_STARTED"
    summary = unit_test_report.get("summary") or {}
    coverage = unit_test_report.get("coverage") or {}
    generated_files = unit_test_report.get("generatedFiles") or []
    failures = unit_test_report.get("failures") or []
    inventory = unit_test_report.get("inventory") or {}

    passed = int(summary.get("passedTests") or 0)
    failed = int(summary.get("failedTests") or 0)
    tests_run = passed + failed

    existing_test_files = [
        entry.get("sourcePath") for entry in (inventory.get("testClasses") or []) if entry.get("sourcePath")
    ]
    generated_test_files = [entry.get("path") for entry in generated_files if entry.get("path")]

    error_summary = unit_test_report.get("errorSummary")
    test_summary_text = error_summary if (status == "FAILED" and error_summary) else _STATUS_MESSAGES.get(status, status)
    test_insights = [
        f"{item.get('testClass', '')}.{item.get('testMethod', '')}: {item.get('reason', '')}".strip(": ")
        for item in failures[:10]
    ]

    bl_coverage = coverage.get("businessLogicLineCoverage")
    jacoco_coverage = coverage.get("jacocoLineCoverage")

    return {
        "tests_run": tests_run,
        "tests_passed": passed,
        "tests_failed": failed,
        "test_summary": test_summary_text,
        "test_insights": test_insights,
        "test_llm_model": unit_test_report.get("llmModel"),
        "bl_coverage": bl_coverage,
        "test_pipeline": {
            "provider": unit_test_report.get("llmProvider") or "groq",
            "project_kind": "JAVA_MAVEN",
            "generated_tests_relative": "src/test/java",
            "test_strategy": "openrewrite_lst_analysis_plus_llm_generation",
            "existing_tests_detected": summary.get("existingTestFiles", 0),
            "existing_test_files": existing_test_files,
            "generated_test_files": generated_test_files,
            "test_summary_metrics": {
                "repo_total_files": summary.get("totalSourceFiles", 0),
                "existing_test_files": summary.get("existingTestFiles", 0),
                "new_test_files": summary.get("newTestFiles", 0),
                "existing_test_cases": summary.get("existingTestCases", 0),
                "generated_test_cases": summary.get("generatedTestCases", 0),
                "total_test_cases": summary.get("totalTestCases", 0),
            },
            "runner": {
                "status": status,
                "buildTool": unit_test_report.get("buildTool"),
                "buildStatus": unit_test_report.get("buildStatus"),
            },
            "coverage_result": {
                "available": bool(coverage.get("jacocoCoverageAvailable")),
                "line_coverage_pct": jacoco_coverage,
                "line_coverage": jacoco_coverage,
                "branch_coverage_pct": coverage.get("branchCoverage"),
                "reason": coverage.get("jacocoCoverageReason"),
            },
        },
    }
