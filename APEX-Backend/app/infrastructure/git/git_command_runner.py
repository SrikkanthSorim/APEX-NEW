"""Runs git commands via the shared command runner.

Keeps git invocation details (flags, credential-free environment) in one place.
Tokens are never passed as CLI args or environment that could leak; when needed
they are embedded in the clone URL by the caller, which is responsible for
masking them in logs.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.core.config import settings
from app.shared.command_runner import CommandResult, run_command


class GitCommandRunner:
    """Thin git wrapper (clone only, for the Discovery stage)."""

    def clone(
        self,
        clone_url: str,
        target_dir: Path,
        *,
        depth: int | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        """Shallow-clone ``clone_url`` into ``target_dir``.

        Runs non-interactively so a missing/invalid credential fails fast
        instead of prompting.
        """
        depth = depth if depth is not None else settings.git_clone_depth
        timeout = timeout if timeout is not None else settings.git_clone_timeout_seconds

        command = [
            "git",
            # Scoped (not global) so it only affects this clone; needed on
            # Windows where some repos (e.g. apache/struts) have paths
            # longer than the default 260-char MAX_PATH, which otherwise
            # fails checkout with "Filename too long" after the clone
            # itself has already succeeded.
            "-c",
            "core.longpaths=true",
            "clone",
            "--depth",
            str(depth),
            "--single-branch",
            clone_url,
            str(target_dir),
        ]

        # Disable interactive credential prompts so private repos without a
        # valid token fail immediately rather than hanging.
        env = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
        }

        return run_command(command, timeout=timeout, env=env)
