"""Builds the frontend-facing MigrationJobSummary / MigrationResult payloads.

The migration's internal state lives in ``migration-report.json`` (see
StartMigrationUseCase). These builders translate that state into the exact shapes
the Result page expects, filling out-of-scope fields (sonar/fossa/tests/diffs)
with safe zero/null defaults so the UI renders without crashing.
"""

from __future__ import annotations

from typing import Any


def _core(report: dict[str, Any]) -> dict[str, Any]:
    """Fields shared by summary + detail."""
    log_lines = report.get("logLines") or []
    return {
        "job_id": report.get("jobId", ""),
        "status": report.get("status", "queued"),
        "source_repo": report.get("sourceRepoUrl") or "",
        "target_repo": report.get("targetRepo"),
        "source_java_version": str(report.get("sourceJavaVersion") or ""),
        "target_java_version": str(report.get("targetJavaVersion") or ""),
        "conversion_types": report.get("conversionTypes") or [],
        "started_at": report.get("startedAt") or "",
        "worker_started_at": report.get("startedAt"),
        "completed_at": report.get("completedAt"),
        "progress_percent": int(report.get("progressPercent") or 0),
        "current_step": report.get("currentStep") or "",
        "files_modified": int(report.get("filesModified") or 0),
        "error_message": report.get("errorMessage"),
        "dependency_count": int(report.get("dependencyCount") or 0),
    }


# All the numeric/nullable analysis fields we don't produce — zeroed defaults.
_ZERO_ANALYSIS = {
    "issues_fixed": 0,
    "api_endpoints_validated": 0,
    "api_endpoints_working": 0,
    "tests_run": 0,
    "tests_passed": 0,
    "tests_failed": 0,
    "sonar_quality_gate": None,
    "sonar_bugs": 0,
    "sonar_vulnerabilities": 0,
    "sonar_code_smells": 0,
    "sonar_coverage": 0,
    "sonar_duplications": 0,
    "sonar_security_hotspots": 0,
    "sonar_scan_mode": None,
    "sonar_real_scan": False,
    "sonar_analysis_url": None,
    "sonar_error_message": None,
    "fossa_policy_status": None,
    "fossa_total_dependencies": 0,
    "fossa_license_issues": 0,
    "fossa_vulnerabilities": 0,
    "fossa_outdated_dependencies": 0,
    "fossa_scan_mode": None,
    "fossa_real_scan": False,
    "fossa_analysis_url": None,
    "fossa_error_message": None,
    "total_errors": 0,
    "total_warnings": 0,
    "errors_fixed": 0,
    "warnings_fixed": 0,
}


def build_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Shape a `MigrationJobSummary`."""
    core = _core(report)
    log_lines = report.get("logLines") or []
    return {
        **core,
        **_ZERO_ANALYSIS,
        "api_endpoint_count": 0,
        "issue_count": 0,
        "log_entry_count": len(log_lines),
        "file_diff_count": 0,
        "has_test_pipeline": False,
        "has_sonar_report": False,
        "has_fossa_report": False,
        "has_testcase_doc": False,
        "has_clone_path": True,
    }


def build_result(report: dict[str, Any]) -> dict[str, Any]:
    """Shape a `MigrationResult` (superset of the summary)."""
    core = _core(report)
    log_lines = report.get("logLines") or []
    return {
        **core,
        **_ZERO_ANALYSIS,
        "dependencies": [],
        "migration_log": log_lines,
        "issues": [],
        "file_diffs": [],
        "test_insights": [],
        "test_summary": None,
        "test_llm_model": None,
        "sonar_report": None,
        "fossa_report": None,
        "test_pipeline": None,
    }


def build_logs(report: dict[str, Any]) -> dict[str, Any]:
    """Shape the `/logs` response."""
    return {
        "job_id": report.get("jobId", ""),
        "logs": report.get("logLines") or [],
    }
