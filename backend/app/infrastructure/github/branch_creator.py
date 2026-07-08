"""Pushes the migrated code as a new branch to an existing repository.

Minimal support for the EXISTING_REPO_BRANCH destination mode. Best-effort:
requires the target token to have write access to the target repo.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import PushFailedError
from app.infrastructure.github.repo_pusher import RepoPusher
from app.shared.command_runner import resolve_executable, run_command

logger = logging.getLogger(__name__)


class BranchCreator:
    def __init__(self, pusher: RepoPusher | None = None) -> None:
        self._pusher = pusher or RepoPusher()

    def push_branch(self, repo_dir: Path, repo_https_url: str, branch: str, *, commit_message: str) -> str:
        """Commit ``repo_dir`` and push it as ``branch`` to an existing repo."""
        token = (settings.github_target_token or "").strip()
        if not token:
            raise PushFailedError("No target GitHub token configured. Set GITHUB_TARGET_TOKEN.")

        git = resolve_executable("git") or "git"
        auth_url = self._pusher._build_auth_url(repo_https_url, token)  # noqa: SLF001 - reuse

        for args in (
            ["init", "-q"],
            ["symbolic-ref", "HEAD", f"refs/heads/{branch}"],
            ["config", "user.name", settings.migration_commit_author_name],
            ["config", "user.email", settings.migration_commit_author_email],
            ["add", "-A"],
            ["commit", "-q", "-m", commit_message],
            ["remote", "add", "origin", auth_url],
            ["push", "-u", "origin", branch],
        ):
            result = run_command([git, *args], cwd=repo_dir, timeout=settings.git_clone_timeout_seconds)
            if not result.succeeded:
                logger.warning("git %s failed during branch push", args[0])
                raise PushFailedError(
                    "Failed to push the migration branch. Check the target token/permissions."
                )
        return branch
