"""FOSSA quality-gate integration."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FossaScanResult:
    policy_status: str | None = None
    total_dependencies: int = 0
    license_issues: int = 0
    vulnerabilities: int = 0
    outdated_dependencies: int = 0
    scan_mode: str = "skipped"
    real_scan: bool = False
    analysis_url: str | None = None
    error_message: str | None = None
    report: dict[str, Any] | None = None
    log_lines: list[str] = field(default_factory=list)


class DependencyCheckRunner:
    """Runs FOSSA analysis when a FOSSA API key is configured."""

    def run(self, project_dir: Path, *, job_id: str, project_name: str | None = None) -> FossaScanResult:
        api_key = settings.fossa_api_key.strip()
        if not api_key:
            return FossaScanResult(
                policy_status="UNAVAILABLE",
                scan_mode="missing_token",
                error_message="Set FOSSA_API_KEY to enable FOSSA quality gate scans.",
                log_lines=["FOSSA skipped: FOSSA_API_KEY is not configured."],
            )

        cli = self._resolve_command(settings.fossa_cli_command)
        if not cli:
            return FossaScanResult(
                policy_status="UNAVAILABLE",
                scan_mode="missing_cli",
                error_message="FOSSA CLI was not found on PATH.",
                log_lines=["FOSSA skipped: fossa CLI was not found on PATH."],
            )

        project = self._project_name(job_id, project_name or project_dir.name)
        env = os.environ.copy()
        env["FOSSA_API_KEY"] = api_key
        if settings.fossa_endpoint.strip():
            env["FOSSA_ENDPOINT"] = settings.fossa_endpoint.strip()

        logger.info("Running FOSSA analysis for job %s with project %s", job_id, project)
        analyze = subprocess.run(
            [cli, "analyze", "--project", project],
            cwd=project_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        analyze_lines = self._redact((analyze.stdout + "\n" + analyze.stderr).splitlines(), api_key)
        if analyze.returncode != 0:
            return FossaScanResult(
                policy_status="FAILED",
                scan_mode="cli_failed",
                real_scan=True,
                error_message="FOSSA analysis failed. Check migration logs for details.",
                log_lines=["FOSSA analysis failed."] + analyze_lines[-20:],
            )

        test = subprocess.run(
            [cli, "test", "--project", project, "--format", "json"],
            cwd=project_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        test_lines = self._redact((test.stdout + "\n" + test.stderr).splitlines(), api_key)
        parsed = self._parse_json_output(test.stdout)
        counts = self._count_findings(parsed)
        status = "PASSED" if test.returncode == 0 else "FAILED"
        report = {
            "project": project,
            "policy_status": status,
            "issue_count": counts["issues"],
            "license_issues": counts["licenses"],
            "vulnerabilities": counts["vulnerabilities"],
            "raw": parsed,
        }

        return FossaScanResult(
            policy_status=status,
            license_issues=counts["licenses"],
            vulnerabilities=counts["vulnerabilities"],
            total_dependencies=counts["dependencies"],
            outdated_dependencies=counts["outdated"],
            scan_mode="real",
            real_scan=True,
            analysis_url=self._analysis_url(project),
            error_message=None if status == "PASSED" else "FOSSA policy check failed.",
            report=report,
            log_lines=["FOSSA analysis completed.", f"FOSSA policy status: {status}"] + analyze_lines[-8:] + test_lines[-12:],
        )

    @staticmethod
    def _resolve_command(command: str) -> str | None:
        command = command.strip()
        if not command:
            return None
        if Path(command).exists():
            return command
        return shutil.which(command)

    @staticmethod
    def _project_name(job_id: str, name: str) -> str:
        seed = f"java-apex-{job_id}-{name}"
        return re.sub(r"[^A-Za-z0-9_.:-]+", "-", seed).strip("-")[:180]

    @staticmethod
    def _analysis_url(project: str) -> str | None:
        endpoint = settings.fossa_endpoint.rstrip("/") if settings.fossa_endpoint else "https://app.fossa.com"
        return f"{endpoint}/projects/custom%2B{project}"

    @staticmethod
    def _redact(lines: list[str], secret: str) -> list[str]:
        if not secret:
            return lines
        return [line.replace(secret, "***") for line in lines if line.strip()]

    @staticmethod
    def _parse_json_output(output: str) -> Any:
        output = output.strip()
        if not output:
            return None
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return None

    def _count_findings(self, payload: Any) -> dict[str, int]:
        counts = {"issues": 0, "licenses": 0, "vulnerabilities": 0, "dependencies": 0, "outdated": 0}
        self._walk(payload, counts)
        return counts

    def _walk(self, value: Any, counts: dict[str, int]) -> None:
        if isinstance(value, list):
            counts["issues"] += len(value)
            for item in value:
                self._walk(item, counts)
            return
        if not isinstance(value, dict):
            return

        lowered = {str(key).lower(): item for key, item in value.items()}
        if any(key in lowered for key in ("dependency", "dependencyname", "locator", "revision")):
            counts["dependencies"] += 1
        text = json.dumps(value, default=str).lower()
        if "license" in text:
            counts["licenses"] += 1
        if any(word in text for word in ("vulnerability", "cve-", "severity")):
            counts["vulnerabilities"] += 1
        if "outdated" in text:
            counts["outdated"] += 1

        for item in value.values():
            self._walk(item, counts)
