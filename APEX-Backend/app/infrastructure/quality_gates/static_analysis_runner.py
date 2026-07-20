"""SonarQube quality-gate integration."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SonarScanResult:
    quality_gate: str | None = None
    bugs: int = 0
    vulnerabilities: int = 0
    code_smells: int = 0
    coverage: float = 0
    duplications: float = 0
    security_hotspots: int = 0
    scan_mode: str = "skipped"
    real_scan: bool = False
    analysis_url: str | None = None
    error_message: str | None = None
    report: dict[str, Any] | None = None
    log_lines: list[str] = field(default_factory=list)


class StaticAnalysisRunner:
    """Runs SonarQube/SonarCloud analysis when credentials are configured."""

    def run(self, project_dir: Path, *, job_id: str, project_name: str | None = None) -> SonarScanResult:
        token = settings.sonarqube_token.strip()
        if not token:
            return SonarScanResult(
                quality_gate="UNAVAILABLE",
                scan_mode="missing_token",
                error_message="Set SONAR_TOKEN to enable SonarQube quality gate scans.",
                log_lines=["SonarQube skipped: SONAR_TOKEN is not configured."],
            )

        scanner = self._resolve_command(settings.sonarqube_scanner_command)
        if not scanner:
            return SonarScanResult(
                quality_gate="UNAVAILABLE",
                scan_mode="missing_cli",
                error_message="sonar-scanner CLI was not found on PATH.",
                log_lines=["SonarQube skipped: sonar-scanner CLI was not found on PATH."],
            )

        project_key = self._project_key(job_id, project_name or project_dir.name)
        host_url = settings.sonarqube_host_url.rstrip("/")
        analysis_url = f"{host_url}/dashboard?id={urllib.parse.quote(project_key)}"

        command = [
            scanner,
            f"-Dsonar.projectKey={project_key}",
            f"-Dsonar.projectName={project_name or project_dir.name}",
            "-Dsonar.sources=.",
            f"-Dsonar.host.url={host_url}",
        ]
        if settings.sonarqube_organization.strip():
            command.append(f"-Dsonar.organization={settings.sonarqube_organization.strip()}")
        env = os.environ.copy()
        env["SONAR_TOKEN"] = token
        env["SONAR_HOST_URL"] = host_url

        logger.info("Running SonarQube scan for job %s with project key %s", job_id, project_key)
        completed = subprocess.run(
            command,
            cwd=project_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        output_lines = self._redact((completed.stdout + "\n" + completed.stderr).splitlines(), token)

        if completed.returncode != 0:
            return SonarScanResult(
                quality_gate="FAILED",
                scan_mode="cli_failed",
                real_scan=True,
                analysis_url=analysis_url,
                error_message="SonarQube scanner failed. Check migration logs for details.",
                log_lines=["SonarQube scan failed."] + output_lines[-20:],
            )

        api_data = self._read_sonar_api(host_url, token, project_key)
        report = {
            "project_key": project_key,
            "analysis_url": analysis_url,
            "quality_gate": api_data.get("quality_gate"),
            "measures": api_data.get("measures", {}),
            "issues": api_data.get("issues", {}),
        }
        return SonarScanResult(
            quality_gate=api_data.get("quality_gate") or "PASSED",
            bugs=int(api_data.get("issues", {}).get("bugs") or 0),
            vulnerabilities=int(api_data.get("issues", {}).get("vulnerabilities") or 0),
            code_smells=int(api_data.get("issues", {}).get("code_smells") or 0),
            coverage=float(api_data.get("measures", {}).get("coverage") or 0),
            duplications=float(api_data.get("measures", {}).get("duplicated_lines_density") or 0),
            security_hotspots=int(api_data.get("issues", {}).get("security_hotspots") or 0),
            scan_mode="real",
            real_scan=True,
            analysis_url=analysis_url,
            report=report,
            log_lines=["SonarQube scan completed.", f"SonarQube dashboard: {analysis_url}"] + output_lines[-10:],
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
    def _project_key(job_id: str, name: str) -> str:
        if settings.sonarqube_project_key.strip():
            return settings.sonarqube_project_key.strip()
        seed = f"{settings.sonarqube_project_key_prefix}-{job_id}-{name}"
        return re.sub(r"[^A-Za-z0-9_.:-]+", "-", seed).strip("-")[:180]

    @staticmethod
    def _redact(lines: list[str], token: str) -> list[str]:
        if not token:
            return lines
        return [line.replace(token, "***") for line in lines if line.strip()]

    def _read_sonar_api(self, host_url: str, token: str, project_key: str) -> dict[str, Any]:
        data: dict[str, Any] = {"issues": {}, "measures": {}}
        try:
            gate_path = "/api/qualitygates/project_status?" + urllib.parse.urlencode({"projectKey": project_key})
            gate = self._get_json(host_url + gate_path, token)
            status = (gate.get("projectStatus") or {}).get("status")
            if status:
                data["quality_gate"] = status
        except Exception as exc:  # noqa: BLE001 - scanner result is still useful
            logger.warning("Unable to read SonarQube quality gate: %s", exc)

        issue_types = {
            "bugs": "BUG",
            "vulnerabilities": "VULNERABILITY",
            "code_smells": "CODE_SMELL",
            "security_hotspots": "SECURITY_HOTSPOT",
        }
        for metric, sonar_type in issue_types.items():
            try:
                path = "/api/issues/search?" + urllib.parse.urlencode(
                    {"componentKeys": project_key, "types": sonar_type, "ps": 1}
                )
                payload = self._get_json(host_url + path, token)
                data["issues"][metric] = int(payload.get("total") or 0)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Unable to read SonarQube issue metric %s: %s", metric, exc)

        try:
            metrics = "coverage,duplicated_lines_density"
            path = "/api/measures/component?" + urllib.parse.urlencode(
                {"component": project_key, "metricKeys": metrics}
            )
            payload = self._get_json(host_url + path, token)
            for measure in (payload.get("component") or {}).get("measures") or []:
                data["measures"][measure.get("metric")] = float(measure.get("value") or 0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unable to read SonarQube measure metrics: %s", exc)

        return data

    @staticmethod
    def _get_json(url: str, token: str) -> dict[str, Any]:
        auth = base64.b64encode(f"{token}:".encode("utf-8")).decode("ascii")
        request = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - configured host URL
            return json.loads(response.read().decode("utf-8"))
