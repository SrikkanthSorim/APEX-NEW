"""Filesystem helpers used by the Discovery analyzers and workspace layer.

All functions are read-only with respect to the analyzed project — nothing here
modifies the cloned repository.
"""

from __future__ import annotations

import shutil
import stat
from pathlib import Path


def read_text(path: Path) -> str:
    """Read a text file, tolerating odd encodings. Returns "" if unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        try:
            return path.read_text(encoding="latin-1")
        except OSError:
            return ""


def exists(root: Path, *relative_parts: str) -> bool:
    """True if ``root/relative_parts...`` exists."""
    return (root.joinpath(*relative_parts)).exists()


def count_files(root: Path, suffix: str, *, limit: int | None = None) -> int:
    """Count files under ``root`` whose name ends with ``suffix`` (case-insensitive).

    Skips common noise directories (VCS, node_modules, build output). Stops early
    once ``limit`` is reached when provided.
    """
    count = 0
    for path in _iter_files(root):
        if path.name.lower().endswith(suffix.lower()):
            count += 1
            if limit is not None and count >= limit:
                break
    return count


def find_files(root: Path, suffix: str, *, limit: int = 2000) -> list[str]:
    """Return repo-relative paths of files ending with ``suffix`` (case-insensitive)."""
    matches: list[str] = []
    lowered = suffix.lower()
    for path in _iter_files(root):
        if path.name.lower().endswith(lowered):
            matches.append(path.relative_to(root).as_posix())
            if len(matches) >= limit:
                break
    return matches


_SKIP_DIRS = {
    ".git",
    "node_modules",
    "target",
    "build",
    "dist",
    ".gradle",
    ".idea",
    ".mvn",
    "out",
    "bin",
}


def _iter_files(root: Path):
    """Yield files under ``root`` skipping noise directories."""
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        # Skip anything inside a noise directory.
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        yield path


def remove_tree(path: Path) -> None:
    """Recursively delete ``path`` if it exists.

    Handles Windows read-only files (common inside ``.git``) via an onerror hook.
    """
    if not path.exists():
        return

    def _on_error(func, target, _exc_info):  # pragma: no cover - platform specific
        try:
            Path(target).chmod(stat.S_IWRITE)
            func(target)
        except OSError:
            pass

    shutil.rmtree(path, onerror=_on_error)
