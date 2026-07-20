"""Coordinates optional Quality Gate scans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.infrastructure.quality_gates.dependency_check_runner import (
    DependencyCheckRunner,
    FossaScanResult,
)
from app.infrastructure.quality_gates.static_analysis_runner import (
    SonarScanResult,
    StaticAnalysisRunner,
)


@dataclass(frozen=True)
class QualityGateResult:
    sonar: SonarScanResult | None = None
    fossa: FossaScanResult | None = None

    @property
    def log_lines(self) -> list[str]:
        lines: list[str] = []
        if self.sonar:
            lines.extend(self.sonar.log_lines)
        if self.fossa:
            lines.extend(self.fossa.log_lines)
        return lines


class QualityGateRunner:
    def __init__(
        self,
        sonar_runner: StaticAnalysisRunner | None = None,
        fossa_runner: DependencyCheckRunner | None = None,
    ) -> None:
        self._sonar_runner = sonar_runner or StaticAnalysisRunner()
        self._fossa_runner = fossa_runner or DependencyCheckRunner()

    def run(
        self,
        project_dir: Path,
        *,
        job_id: str,
        project_name: str | None = None,
        run_sonar: bool = False,
        run_fossa: bool = False,
    ) -> QualityGateResult:
        sonar = (
            self._sonar_runner.run(project_dir, job_id=job_id, project_name=project_name)
            if run_sonar
            else None
        )
        fossa = (
            self._fossa_runner.run(project_dir, job_id=job_id, project_name=project_name)
            if run_fossa
            else None
        )
        return QualityGateResult(sonar=sonar, fossa=fossa)
