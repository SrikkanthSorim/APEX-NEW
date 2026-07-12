"""Diffs the original repo against the migrated repo to report what changed.

Read-only: only inspects file bytes/text on both trees, never modifies either.
Used after OpenRewrite/build-config modernization runs so the migration report
can state exactly which files, imports, and source lines were touched.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from app.shared import file_utils

_IMPORT_RE_PREFIX = "import "
_MAX_TRACKED_FILES = 300


@dataclass(frozen=True)
class ImportChange:
    file: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"file": self.file, "added": self.added, "removed": self.removed}


@dataclass(frozen=True)
class SourceChange:
    file: str
    lines_changed: int

    def to_dict(self) -> dict[str, object]:
        return {"file": self.file, "linesChanged": self.lines_changed}


@dataclass(frozen=True)
class ChangeAnalysis:
    added_files: list[str] = field(default_factory=list)
    removed_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    import_changes: list[ImportChange] = field(default_factory=list)
    source_changes: list[SourceChange] = field(default_factory=list)

    @property
    def all_changed_files(self) -> list[str]:
        return sorted({*self.added_files, *self.removed_files, *self.modified_files})

    @property
    def files_modified_count(self) -> int:
        return len(self.all_changed_files)


class ChangeAnalyzer:
    def analyze(self, original: Path, migrated: Path) -> ChangeAnalysis:
        added, removed, modified = file_utils.diff_relative_files(original, migrated)

        import_changes: list[ImportChange] = []
        source_changes: list[SourceChange] = []

        java_modified = [rel for rel in modified if rel.endswith(".java")][:_MAX_TRACKED_FILES]
        java_added = [rel for rel in added if rel.endswith(".java")][:_MAX_TRACKED_FILES]

        for rel in java_modified:
            original_text = file_utils.read_text(original / rel)
            migrated_text = file_utils.read_text(migrated / rel)
            import_change = self._import_diff(rel, original_text, migrated_text)
            if import_change:
                import_changes.append(import_change)
            changed_lines = self._non_import_lines_changed(original_text, migrated_text)
            if changed_lines:
                source_changes.append(SourceChange(rel, changed_lines))

        for rel in java_added:
            migrated_text = file_utils.read_text(migrated / rel)
            import_change = self._import_diff(rel, "", migrated_text)
            if import_change:
                import_changes.append(import_change)

        return ChangeAnalysis(
            added_files=added,
            removed_files=removed,
            modified_files=modified,
            import_changes=import_changes,
            source_changes=source_changes,
        )

    @staticmethod
    def _imports_of(text: str) -> list[str]:
        seen: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(_IMPORT_RE_PREFIX) and stripped.endswith(";"):
                statement = stripped[len(_IMPORT_RE_PREFIX):-1].strip()
                if statement and statement not in seen:
                    seen.append(statement)
        return seen

    def _import_diff(self, rel: str, original_text: str, migrated_text: str) -> ImportChange | None:
        original_imports = self._imports_of(original_text)
        migrated_imports = self._imports_of(migrated_text)
        added = [imp for imp in migrated_imports if imp not in original_imports]
        removed = [imp for imp in original_imports if imp not in migrated_imports]
        if not added and not removed:
            return None
        return ImportChange(file=rel, added=added, removed=removed)

    @staticmethod
    def _non_import_lines_changed(original_text: str, migrated_text: str) -> int:
        original_lines = [
            line for line in original_text.splitlines() if not line.strip().startswith(_IMPORT_RE_PREFIX)
        ]
        migrated_lines = [
            line for line in migrated_text.splitlines() if not line.strip().startswith(_IMPORT_RE_PREFIX)
        ]
        diff = difflib.unified_diff(original_lines, migrated_lines, lineterm="")
        return sum(
            1 for line in diff
            if (line.startswith("+") or line.startswith("-"))
            and not line.startswith(("+++", "---"))
        )
