"""Manages the on-disk workspace folders for a job.

Creates the job's directory tree and provides a clean ``original-repo`` target
for cloning. It never touches ``reports/`` contents (owned by the persistence
layer) beyond ensuring the folder exists.
"""

from __future__ import annotations

import logging

from app.infrastructure.workspace.workspace_paths import WorkspacePaths
from app.shared import file_utils

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
