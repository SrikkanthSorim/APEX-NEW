"""Pushes the migrated-repo to a target repository as a fresh single commit.

The token is embedded in the remote URL only for the push and is always masked
in logs. No source git history is carried over.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import PushFailedError
from app.shared.command_runner import CommandResult, resolve_executable, run_command

logger = logging.getLogger(__name__)

_TOKEN_MASK = "***"


class RepoPusher:
    def push(
        self,
        repo_dir: Path,
        clone_url: str,
        *,
        commit_message: str,
        branch: str = "main",
        allow_force_update_existing: bool = False,
    ) -> str:
        """Init, commit, and push ``repo_dir`` to ``clone_url``. Returns the branch."""
        token = (settings.github_target_token or "").strip()
        if not token:
            raise PushFailedError("No target GitHub token configured. Set GITHUB_TARGET_TOKEN.")

        auth_url = self._build_auth_url(clone_url, token)

        self._git(repo_dir, ["init", "-q"])
        self._git(repo_dir, ["symbolic-ref", "HEAD", f"refs/heads/{branch}"])
        self._git(repo_dir, ["config", "user.name", settings.migration_commit_author_name])
        self._git(repo_dir, ["config", "user.email", settings.migration_commit_author_email])
        self._git(repo_dir, ["add", "-A"])
        self._git(repo_dir, ["commit", "-q", "-m", commit_message])
        self._git(repo_dir, ["remote", "add", "origin", auth_url], sensitive=True)
        logger.info("Pushing migrated repo to %s", self._mask(clone_url))
        push_result = self._run_git(repo_dir, ["push", "-u", "origin", branch])
        if push_result.succeeded:
            return branch

        if allow_force_update_existing and self._is_non_fast_forward(push_result.stderr):
            logger.warning(
                "Remote %s already has %s; retrying with --force-with-lease.",
                self._mask(clone_url),
                branch,
            )
            self._run_git(
                repo_dir,
                ["fetch", "origin", f"{branch}:refs/remotes/origin/{branch}", "--depth=1"],
            )
            force_result = self._run_git(
                repo_dir,
                ["push", "--force-with-lease", "-u", "origin", branch],
            )
            if force_result.succeeded:
                return branch
            self._raise_git_failure(force_result, action="push")

        self._raise_git_failure(push_result, action="push")
        return branch

    # -- helpers ------------------------------------------------------------- #

    def _git(self, cwd: Path, args: list[str], *, sensitive: bool = False) -> CommandResult:
        result = self._run_git(cwd, args)
        if not result.succeeded:
            self._raise_git_failure(result, action="push" if sensitive else " ".join(args[:1]))
        return result

    def _run_git(self, cwd: Path, args: list[str]) -> CommandResult:
        git = resolve_executable("git") or "git"
        return run_command([git, *args], cwd=cwd, timeout=settings.git_clone_timeout_seconds)

    def _raise_git_failure(self, result: CommandResult, *, action: str) -> None:
        stderr = self._mask(result.stderr.strip())
        logger.warning("git %s failed: %s", action, stderr)
        raise PushFailedError(
            "Failed to publish the migrated repository. Check the target token/permissions."
        )

    @staticmethod
    def _is_non_fast_forward(stderr: str) -> bool:
        lowered = (stderr or "").lower()
        return "fetch first" in lowered or "non-fast-forward" in lowered or "[rejected]" in lowered

    @staticmethod
    def _build_auth_url(https_url: str, token: str) -> str:
        url = https_url.strip()
        if not url.endswith(".git"):
            url = f"{url.rstrip('/')}.git"
        return url.replace("https://", f"https://x-access-token:{token}@", 1)

    @staticmethod
    def _mask(text: str) -> str:
        if not text:
            return text
        return re.sub(r"(https://)[^@/\s]+@", rf"\1{_TOKEN_MASK}@", text)
