"""Builds the frontend-facing MigrationJobSummary / MigrationResult payloads.

The migration's internal state lives in ``migration-report.json`` (see
StartMigrationUseCase). These builders translate that state into the exact shapes
the Result page expects, filling out-of-scope fields (sonar/fossa/tests/diffs)
with safe zero/null defaults so the UI renders without crashing.
"""

from __future__ import annotations

from typing import Any

from app.shared import migration_log_sanitizer as sanitizer


def _sanitized_skipped_recipes(report: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for item in report.get("skippedRecipes") or []:
        item = dict(item)
        if item.get("recipes"):
            item["recipes"] = sanitizer.humanize_recipe_names(item["recipes"])
        if item.get("reason"):
            item["reason"] = sanitizer.sanitize_text(item["reason"])
        result.append(item)
    return result


def _sanitized_retry_attempts(report: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for item in report.get("retryAttempts") or []:
        item = dict(item)
        if item.get("rootCause"):
            item["rootCause"] = sanitizer.sanitize_text(item["rootCause"])
        if item.get("recipesAdded"):
            item["recipesAdded"] = sanitizer.humanize_recipe_names(item["recipesAdded"])
        result.append(item)
    return result


def _core(report: dict[str, Any]) -> dict[str, Any]:
    """Fields shared by summary + detail.

    Raw OpenRewrite/Maven/Gradle internals are stripped here, at the single
    boundary every API response (and, transitively, the generated project
    documentation) is built from -- see ``migration_log_sanitizer``.
    """
    return {
        "job_id": report.get("jobId", ""),
        "status": report.get("status", "queued"),
        "source_repo": report.get("sourceRepoUrl") or "",
        "target_repo": report.get("targetRepo"),
        "source_java_version": str(report.get("sourceJavaVersion") or ""),
        "target_java_version": str(report.get("targetJavaVersion") or ""),
        "effective_target_java_version": str(
            report.get("effectiveTargetJavaVersion")
            or report.get("targetJavaVersion")
            or ""
        ),
        "conversion_types": report.get("conversionTypes") or [],
        "started_at": report.get("startedAt") or "",
        "worker_started_at": report.get("startedAt"),
        "completed_at": report.get("completedAt"),
        "progress_percent": int(report.get("progressPercent") or 0),
        "current_step": report.get("currentStep") or "",
        "files_modified": int(report.get("filesModified") or 0),
        "error_message": sanitizer.sanitize_text(report.get("errorMessage")) or None,
        "dependency_count": int(report.get("dependencyCount") or 0),
        # --- migration engine report fields (sanitized: no recipe class
        # names / OpenRewrite internals reach the API from here) ---
        "recipes_executed": sanitizer.humanize_recipe_names(report.get("recipes") or []),
        "recipe_selection_reasons": sanitizer.sanitize_lines(report.get("recipeSelection") or []),
        "build_modernization": [
            sanitizer.sanitize_text(line) for line in (report.get("buildModernization") or [])
        ],
        "dependency_upgrades": report.get("dependencyUpgrades") or [],
        "used_fallback": bool(report.get("usedFallback")),
        "already_compatible": bool(report.get("alreadyCompatible")),
        "build_status": report.get("buildStatus"),
        "build_success": report.get("buildSuccess"),
        "migration_summary": sanitizer.sanitize_text(report.get("migrationSummary")) or "",
        "retry_attempts": _sanitized_retry_attempts(report),
        "migration_phases": report.get("migrationPhases") or [],
        "skipped_recipes": _sanitized_skipped_recipes(report),
        "spring_source_framework": report.get("springSourceFramework") or "",
        "spring_target_framework": report.get("springTargetFramework") or "",
        "spring_boot_version_before": report.get("springBootVersionBefore"),
        "spring_boot_version_after": report.get("springBootVersionAfter"),
        "spring_conversion_requested": bool(report.get("springConversionRequested")),
        "spring_conversion_supported": report.get("springConversionSupported"),
        "spring_conversion_note": sanitizer.sanitize_text(report.get("springConversionNote")) or None,
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


def _analysis(report: dict[str, Any]) -> dict[str, Any]:
    """Overlay produced analysis fields on top of stable UI defaults."""
    values = dict(_ZERO_ANALYSIS)
    for key in values:
        if key in report:
            values[key] = report.get(key)
    return values


def build_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Shape a `MigrationJobSummary`."""
    core = _core(report)
    log_lines = sanitizer.sanitize_lines(report.get("logLines") or [])
    return {
        **core,
        **_analysis(report),
        "api_endpoint_count": 0,
        "issue_count": 0,
        "log_entry_count": len(log_lines),
        "file_diff_count": 0,
        "has_test_pipeline": False,
        "has_sonar_report": bool(report.get("sonar_report")),
        "has_fossa_report": bool(report.get("fossa_report")),
        "has_testcase_doc": False,
        "has_clone_path": True,
    }


def build_result(report: dict[str, Any]) -> dict[str, Any]:
    """Shape a `MigrationResult` (superset of the summary)."""
    core = _core(report)
    log_lines = sanitizer.sanitize_lines(report.get("logLines") or [])
    return {
        **core,
        **_analysis(report),
        "dependencies": [],
        "migration_log": log_lines,
        "issues": [],
        "file_diffs": [],
        "test_insights": [],
        "test_summary": None,
        "test_llm_model": None,
        "sonar_report": report.get("sonar_report"),
        "fossa_report": report.get("fossa_report"),
        "test_pipeline": None,
        # --- full migration report detail ---
        "modified_files": report.get("modifiedFiles") or [],
        "import_changes": report.get("importChanges") or [],
        "source_changes": report.get("sourceChanges") or [],
    }


def build_logs(report: dict[str, Any]) -> dict[str, Any]:
    """Shape the `/logs` response."""
    return {
        "job_id": report.get("jobId", ""),
        "logs": sanitizer.sanitize_lines(report.get("logLines") or []),
    }


def build_fossa(report: dict[str, Any]) -> dict[str, Any]:
    """Shape the `/fossa` response."""
    return {
        "job_id": report.get("jobId", ""),
        "fossa": report.get("fossa_report"),
    }
