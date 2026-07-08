"""Clones a GitHub repository into a job's ``original-repo`` folder.

Responsibilities are limited to cloning — no analysis, no file modification.
Handles private repos by embedding the token in the clone URL, and always masks
the token in any log output.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.core.exceptions import CloneFailedError
from app.infrastructure.git.git_command_runner import GitCommandRunner

logger = logging.getLogger(__name__)

_TOKEN_MASK = "***"


@dataclass(frozen=True)
class CloneResult:
    target_dir: Path
    default_branch: str | None


class RepositoryCloner:
    """Clones a repo (git clone only)."""

    def __init__(self, git_runner: GitCommandRunner | None = None) -> None:
        self._git = git_runner or GitCommandRunner()

    def clone(
        self,
        repo_url: str,
        target_dir: Path,
        *,
        token: str | None = None,
        log_path: Path | None = None,
    ) -> CloneResult:
        """Clone ``repo_url`` into ``target_dir``.

        Raises :class:`CloneFailedError` (with a clean message) on any failure;
        detailed, token-masked diagnostics are appended to ``log_path``.
        """
        normalized = self._normalize_https_url(repo_url)
        clone_url = self._build_clone_url(normalized, token)
        masked_url = self._mask_token(clone_url)

        logger.info("git clone %s", masked_url)
        self._log(log_path, f"Cloning {masked_url} -> {target_dir}")

        result = self._git.clone(clone_url, target_dir)

        if not result.succeeded:
            stderr = self._mask_token(result.stderr.strip())
            if result.timed_out:
                logger.warning("Clone timed out for %s", masked_url)
                self._log(log_path, "Clone timed out.")
                raise CloneFailedError(
                    "Repository clone timed out. Please try again."
                )
            logger.warning("Clone failed (exit %s) for %s: %s", result.exit_code, masked_url, stderr)
            self._log(log_path, f"Clone failed (exit {result.exit_code}): {stderr}")
            raise CloneFailedError()

        logger.info("git clone completed: %s", masked_url)
        self._log(log_path, "Clone completed successfully.")
        return CloneResult(target_dir=target_dir, default_branch=None)

    # -- helpers ------------------------------------------------------------- #

    @staticmethod
    def _normalize_https_url(repo_url: str) -> str:
        """Return a canonical ``https://github.com/owner/repo.git`` URL."""
        url = repo_url.strip()
        if not url.startswith(("http://", "https://")):
            url = f"https://{url.lstrip('/')}"
        url = url.replace("http://", "https://", 1)
        if not url.endswith(".git"):
            url = f"{url.rstrip('/')}.git"
        return url

    @staticmethod
    def _build_clone_url(https_url: str, token: str | None) -> str:
        """Embed the token for authenticated clones; return as-is for public."""
        token = (token or "").strip()
        if not token:
            return https_url
        # https://x-access-token:<token>@github.com/owner/repo.git
        return https_url.replace("https://", f"https://x-access-token:{token}@", 1)

    @staticmethod
    def _mask_token(text: str) -> str:
        """Redact any embedded credentials in a URL/log line."""
        if not text:
            return text
        # https://user:token@host -> https://***@host
        return re.sub(r"(https://)[^@/\s]+@", rf"\1{_TOKEN_MASK}@", text)

    @staticmethod
    def _log(log_path: Path | None, message: str) -> None:
        if log_path is None:
            return
        timestamp = datetime.now(timezone.utc).isoformat()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
