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


def find_shallowest_dir_with(
    root: Path,
    filenames: tuple[str, ...],
    *,
    max_depth: int = 5,
) -> Path | None:
    """Return the shallowest directory (at or under ``root``) that contains any
    of ``filenames``.

    Used to locate a Java project when its build file lives in a subfolder
    (e.g. ``backend/pom.xml``) rather than the repo root. Noise directories are
    skipped and the search is depth-bounded. Ties at the same depth prefer the
    first match in a stable, sorted order.
    """
    targets = {name.lower() for name in filenames}
    best_dir: Path | None = None
    best_depth: int | None = None

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.lower() not in targets:
            continue
        relative_parts = path.relative_to(root).parts
        if any(part in _SKIP_DIRS for part in relative_parts[:-1]):
            continue
        depth = len(relative_parts) - 1  # number of directories above the file
        if depth > max_depth:
            continue
        if best_depth is None or depth < best_depth:
            best_dir = path.parent
            best_depth = depth
            if depth == 0:
                break  # can't get shallower than the root itself
    return best_dir


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


def _relative_files(root: Path) -> dict[str, Path]:
    """Map of repo-relative posix path -> absolute path (noise dirs skipped)."""
    return {path.relative_to(root).as_posix(): path for path in _iter_files(root)}


def count_changed_files(original: Path, migrated: Path) -> int:
    """Count files that differ between two trees (added, removed, or modified).

    Both trees are compared with noise directories skipped. Used to report how
    many files a migration changed, independent of the build tool's own output.
    """
    original_files = _relative_files(original)
    migrated_files = _relative_files(migrated)

    changed = 0
    for rel in set(original_files) | set(migrated_files):
        a = original_files.get(rel)
        b = migrated_files.get(rel)
        if a is None or b is None:
            changed += 1
            continue
        try:
            if a.read_bytes() != b.read_bytes():
                changed += 1
        except OSError:
            changed += 1
    return changed


def copy_tree(src: Path, dst: Path, *, exclude: set[str] | None = None) -> None:
    """Copy the ``src`` directory tree to ``dst`` (created fresh).

    ``exclude`` names directories to skip at any level (e.g. ``{".git"}``) so the
    copy is a clean working tree without VCS metadata.
    """
    exclude = exclude or set()
    remove_tree(dst)

    def _ignore(_dir: str, names: list[str]) -> set[str]:
        return {name for name in names if name in exclude}

    shutil.copytree(src, dst, ignore=_ignore)
