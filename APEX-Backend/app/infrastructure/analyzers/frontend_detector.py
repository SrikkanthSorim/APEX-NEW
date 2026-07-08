"""Detects the presence and type of a frontend inside the project."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.shared import file_utils

REACT = "REACT"
ANGULAR = "ANGULAR"
VITE_REACT = "VITE_REACT"
JSP = "JSP"
UNKNOWN = "UNKNOWN"

# Directories commonly used to host a frontend, checked in order.
_CANDIDATE_DIRS = ("", "frontend", "client", "web", "ui", "webapp")


@dataclass(frozen=True)
class FrontendResult:
    detected: bool
    type: str
    path: str | None
    package_manager: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "detected": self.detected,
            "type": self.type,
            "path": self.path,
            "packageManager": self.package_manager,
        }


class FrontendDetector:
    def detect(self, root: Path) -> FrontendResult:
        for relative in _CANDIDATE_DIRS:
            base = root if relative == "" else root / relative
            package_json = base / "package.json"
            if package_json.is_file():
                return self._classify_node_frontend(base, relative, package_json)

        # No Node frontend — check for a classic JSP/webapp frontend.
        if file_utils.exists(root, "src", "main", "webapp") or file_utils.count_files(
            root, ".jsp", limit=1
        ) > 0:
            return FrontendResult(True, JSP, "src/main/webapp", None)

        return FrontendResult(False, UNKNOWN, None, None)

    # -- helpers ------------------------------------------------------------- #

    def _classify_node_frontend(
        self, base: Path, relative: str, package_json: Path
    ) -> FrontendResult:
        deps = self._read_package_dependencies(package_json)
        has_vite = self._has_vite(base, deps)

        if "@angular/core" in deps:
            frontend_type = ANGULAR
        elif "react" in deps:
            frontend_type = VITE_REACT if has_vite else REACT
        elif has_vite:
            frontend_type = VITE_REACT
        else:
            frontend_type = UNKNOWN

        path = relative or "."
        return FrontendResult(
            detected=True,
            type=frontend_type,
            path=path,
            package_manager=self._detect_package_manager(base),
        )

    @staticmethod
    def _read_package_dependencies(package_json: Path) -> dict[str, str]:
        try:
            data = json.loads(file_utils.read_text(package_json) or "{}")
        except json.JSONDecodeError:
            return {}
        merged: dict[str, str] = {}
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            block = data.get(key)
            if isinstance(block, dict):
                merged.update({str(k): str(v) for k, v in block.items()})
        return merged

    @staticmethod
    def _has_vite(base: Path, deps: dict[str, str]) -> bool:
        if "vite" in deps:
            return True
        return (base / "vite.config.js").is_file() or (base / "vite.config.ts").is_file()

    @staticmethod
    def _detect_package_manager(base: Path) -> str:
        if (base / "pnpm-lock.yaml").is_file():
            return "pnpm"
        if (base / "yarn.lock").is_file():
            return "yarn"
        return "npm"
