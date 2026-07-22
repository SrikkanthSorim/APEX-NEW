"""Scans real Java source files for a Spring Boot application entry point.

Looks for ``@SpringBootApplication`` and ``SpringApplication.run(...)`` --
the two concrete, code-level signals the Discovery requirements call out,
independent of what the build file declares. Bounded and short-circuiting so
it stays cheap on large repositories: files that look like an entry point by
name (``*Application.java``) are checked first, and the scan stops at the
first match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.shared import file_utils

_ANNOTATION_PATTERN = re.compile(r"@SpringBootApplication\b")
_RUN_CALL_PATTERN = re.compile(r"SpringApplication\s*\.\s*run\s*\(")
_MAX_FILES_SCANNED = 400


@dataclass(frozen=True)
class SpringEntrypointResult:
    found: bool
    entry_class: str | None


class SpringEntrypointScanner:
    def scan(self, project_root: Path, java_files: list[str]) -> SpringEntrypointResult:
        candidates = [f for f in java_files if "/test/" not in f.replace("\\", "/")]
        candidates.sort(key=lambda f: (0 if f.endswith("Application.java") else 1, f))

        for relative_path in candidates[:_MAX_FILES_SCANNED]:
            text = file_utils.read_text(project_root / relative_path)
            if not text:
                continue
            if _ANNOTATION_PATTERN.search(text) or _RUN_CALL_PATTERN.search(text):
                return SpringEntrypointResult(found=True, entry_class=relative_path)

        return SpringEntrypointResult(found=False, entry_class=None)
