from pathlib import Path
from types import SimpleNamespace

from app.domain.models.build_result import BUILD_STATUS_FAILED, BUILD_STATUS_SUCCESS, BUILD_STATUS_TIMEOUT
from app.infrastructure.build.build_validator import BuildValidator
from app.shared.command_runner import CommandResult


def test_build_validator_reports_success_status(monkeypatch):
    monkeypatch.setattr("app.infrastructure.build.build_validator.resolve_executable", lambda name: "mvn")
    monkeypatch.setattr(
        "app.infrastructure.build.build_validator.run_command",
        lambda *args, **kwargs: CommandResult(command=["mvn"], exit_code=0, stdout="BUILD SUCCESS", stderr="", timed_out=False),
    )
    monkeypatch.setattr(
        "app.infrastructure.build.build_validator.parse_build_output",
        lambda stdout, stderr: SimpleNamespace(lines=[stdout], error_lines=[]),
    )

    result = BuildValidator().validate(Path("/tmp/project"), "MAVEN")

    assert result.success is True
    assert result.status == BUILD_STATUS_SUCCESS
    assert result.return_code == 0


def test_build_validator_reports_timeout_status(monkeypatch):
    monkeypatch.setattr("app.infrastructure.build.build_validator.resolve_executable", lambda name: "mvn")
    monkeypatch.setattr(
        "app.infrastructure.build.build_validator.run_command",
        lambda *args, **kwargs: CommandResult(command=["mvn"], exit_code=-1, stdout="", stderr="timed out", timed_out=True),
    )
    monkeypatch.setattr(
        "app.infrastructure.build.build_validator.parse_build_output",
        lambda stdout, stderr: SimpleNamespace(lines=[], error_lines=[stderr]),
    )

    result = BuildValidator().validate(Path("/tmp/project"), "MAVEN")

    assert result.success is False
    assert result.status == BUILD_STATUS_TIMEOUT
    assert result.duration_ms is not None


def test_build_validator_reports_failed_status(monkeypatch):
    monkeypatch.setattr("app.infrastructure.build.build_validator.resolve_executable", lambda name: "mvn")
    monkeypatch.setattr(
        "app.infrastructure.build.build_validator.run_command",
        lambda *args, **kwargs: CommandResult(command=["mvn"], exit_code=1, stdout="", stderr="compile failed", timed_out=False),
    )
    monkeypatch.setattr(
        "app.infrastructure.build.build_validator.parse_build_output",
        lambda stdout, stderr: SimpleNamespace(lines=[], error_lines=[stderr]),
    )

    result = BuildValidator().validate(Path("/tmp/project"), "MAVEN")

    assert result.success is False
    assert result.status == BUILD_STATUS_FAILED
    assert result.safe_summary == "compile failed"
