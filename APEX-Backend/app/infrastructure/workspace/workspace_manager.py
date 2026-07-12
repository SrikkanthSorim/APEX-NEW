"""Manages the on-disk workspace folders for a job.

Creates the job's directory tree and provides a clean ``original-repo`` target
for cloning. It never touches ``reports/`` contents (owned by the persistence
layer) beyond ensuring the folder exists.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.infrastructure.workspace.workspace_paths import WorkspacePaths
from app.shared import file_utils
from app.shared.command_runner import resolve_executable, run_command

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """Prepares and cleans the per-job workspace folders."""

    def __init__(self, paths: WorkspacePaths) -> None:
        self._paths = paths

    def ensure_job_dirs(self) -> None:
        """Ensure reports/ and logs/ exist for the job."""
        self._paths.reports_dir.mkdir(parents=True, exist_ok=True)
        self._paths.logs_dir.mkdir(parents=True, exist_ok=True)

    def prepare_original_repo_target(self) -> None:
        """Ensure ``original-repo`` is absent and its parent exists.

        If a previous clone is present it is removed so the fresh clone starts
        from a clean slate. ``git clone`` requires the target directory not to
        already exist.
        """
        original = self._paths.original_repo_dir
        if original.exists():
            logger.info("Removing existing original-repo before re-clone: %s", original.name)
            file_utils.remove_tree(original)
        original.parent.mkdir(parents=True, exist_ok=True)

    def prepare_migrated_repo(self) -> None:
        """Create a fresh ``migrated-repo`` as a copy of ``original-repo``.

        The copy excludes ``.git`` so OpenRewrite works on a clean working tree
        and the eventual push starts from a single fresh commit. ``original-repo``
        is never modified.
        """
        original = self._paths.original_repo_dir
        migrated = self._paths.migrated_repo_dir
        logger.info("Preparing migrated-repo from original-repo (excluding .git)")
        file_utils.copy_tree(original, migrated, exclude={".git"})
        self._init_git_boundary(migrated)

    @staticmethod
    def _init_git_boundary(migrated: Path) -> None:
        """Give ``migrated-repo`` its own ``.git`` so it is a repository root.

        This job's workspace (``storage/migration-jobs/...``) normally sits
        nested inside this very project's own git working tree. Without a
        ``.git`` of its own here, OpenRewrite's Maven/Gradle plugins walk up
        the filesystem looking for one and land on the *outer* repository
        root instead -- which makes them silently resolve project files
        against the wrong base directory and apply zero recipe changes
        (the build still reports success since compilation doesn't depend on
        this). An empty ``git init`` here gives the walk-up a boundary to
        stop at; ``repo_pusher``'s later ``git init`` on the same directory
        is a no-op against an already-initialized repo.
        """
        git = resolve_executable("git")
        if not git:
            return
        run_command([git, "init", "-q"], cwd=migrated, timeout=30)
