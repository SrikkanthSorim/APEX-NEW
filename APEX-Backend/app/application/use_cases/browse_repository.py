"""Repository file browser use case.

Read-only browsing of a job's already-cloned ``original-repo`` workspace
(created by the Discovery stage). Powers the Discovery page's
"Repository Files" panel — no re-cloning and no GitHub API calls, so it works
identically for public and private repos and never hits GitHub rate limits.
Folder listings are fetched one directory at a time (lazy), so this stays fast
even on very large repositories.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.exceptions import (
    RepositoryFileNotTextError,
    RepositoryFileTooLargeError,
    RepositoryPathInvalidError,
    RepositoryPathNotFoundError,
    RepositoryWorkspaceNotFoundError,
)
from app.infrastructure.workspace.workspace_paths import WorkspacePaths

# Never worth listing/descending into.
_IGNORED_DIR_NAMES = {".git"}

# Safety cap so a huge binary/log file can't be dumped whole into a response.
MAX_PREVIEW_FILE_BYTES = 1_000_000  # ~1 MB


@dataclass(frozen=True)
class RepoFileEntry:
    name: str
    path: str
    type: str  # "file" | "dir"
    size: int


@dataclass(frozen=True)
class RepoFileContent:
    path: str
    content: str
    size: int


class RepositoryFileBrowser:
    def __init__(self, storage_dir: Path | None = None) -> None:
        self._storage_dir = storage_dir

    def _resolve_root(self, job_id: str) -> Path:
        paths = WorkspacePaths(job_id, self._storage_dir)
        root = paths.original_repo_dir
        if not root.is_dir():
            raise RepositoryWorkspaceNotFoundError()
        return root.resolve()

    @staticmethod
    def _resolve_target(root: Path, relative_path: str) -> Path:
        """Resolve ``relative_path`` under ``root``, rejecting any escape (``..``)."""
        cleaned = (relative_path or "").strip().strip("/").replace("\\", "/")
        target = (root / cleaned).resolve() if cleaned else root

        if target != root and root not in target.parents:
            raise RepositoryPathInvalidError()

        return target

    def list_directory(self, job_id: str, relative_path: str = "") -> list[RepoFileEntry]:
        root = self._resolve_root(job_id)
        target = self._resolve_target(root, relative_path)

        if not target.exists():
            raise RepositoryPathNotFoundError()
        if not target.is_dir():
            raise RepositoryPathInvalidError("The requested path is not a folder.")

        entries: list[RepoFileEntry] = []
        for child in target.iterdir():
            if child.name in _IGNORED_DIR_NAMES:
                continue

            is_dir = child.is_dir()
            child_relative = child.relative_to(root).as_posix()
            size = 0 if is_dir else child.stat().st_size
            entries.append(
                RepoFileEntry(
                    name=child.name,
                    path=child_relative,
                    type="dir" if is_dir else "file",
                    size=size,
                )
            )

        # Folders first, then files, both alphabetical — matches the reference
        # GitHub-style file browser UX.
        entries.sort(key=lambda entry: (entry.type != "dir", entry.name.lower()))
        return entries

    def read_file(self, job_id: str, relative_path: str) -> RepoFileContent:
        root = self._resolve_root(job_id)
        target = self._resolve_target(root, relative_path)

        if not target.exists():
            raise RepositoryPathNotFoundError()
        if not target.is_file():
            raise RepositoryPathInvalidError("The requested path is not a file.")

        size = target.stat().st_size
        if size > MAX_PREVIEW_FILE_BYTES:
            raise RepositoryFileTooLargeError()

        raw = target.read_bytes()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise RepositoryFileNotTextError() from None

        return RepoFileContent(path=target.relative_to(root).as_posix(), content=content, size=size)
