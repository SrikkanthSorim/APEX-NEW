"""Shared subprocess runner.

A thin, safe wrapper around :mod:`subprocess` used by the git layer (and any
future external-tool integration). It avoids ``shell=True``, captures
stdout/stderr/exit-code, and supports a timeout — returning a structured result
rather than raising on non-zero exit.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CommandResult:
    """Structured outcome of a command invocation."""

    command: Sequence[str]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def run_command(
    command: Sequence[str],
    *,
    cwd: str | Path | None = None,
    timeout: float | None = None,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    """Run ``command`` (a list of args — never a shell string).

    Never raises on a non-zero exit or timeout; inspect
    :attr:`CommandResult.succeeded`. Only genuinely exceptional conditions
    (e.g. the executable not being found) propagate.
    """
    try:
        completed = subprocess.run(  # noqa: S603 - args list, shell disabled
            list(command),
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=dict(env) if env is not None else None,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=list(command),
            exit_code=-1,
            stdout=exc.stdout or "" if isinstance(exc.stdout, str) else "",
            stderr=exc.stderr or "" if isinstance(exc.stderr, str) else "",
            timed_out=True,
        )

    return CommandResult(
        command=list(command),
        exit_code=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )
