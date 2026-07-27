"""Python wrapper around the standalone ``rewrite-test-inventory`` Java CLI
(see ``tools/rewrite-test-inventory/``), which uses the real OpenRewrite Java
parser/LST -- not regex or filename-only heuristics -- to produce structured
metadata about a project's production and test classes.

Invoked via subprocess, following the exact pattern already used for
mvn/gradle elsewhere in this codebase (``app/shared/command_runner``).
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import UnitTestToolUnavailableError
from app.domain.models.unit_test_report import ProjectInventory
from app.infrastructure.java_runtime import build_tool_env
from app.shared.command_runner import resolve_executable, run_command

logger = logging.getLogger(__name__)

# The tool depends on org.openrewrite:rewrite-java-17, which requires a
# JDK 17+ runtime to execute (it accesses javac internals of that vintage).
MIN_JAVA_MAJOR = 17


def resolve_java_executable() -> str | None:
    """Resolve a JDK 17+ ``java`` executable, shared by every caller of the
    ``rewrite-test-inventory`` jar (inventory scan and generated-test
    validation alike).
    """
    env = build_tool_env(MIN_JAVA_MAJOR)
    java_home = env.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / "java.exe"
        if not candidate.is_file():
            candidate = Path(java_home) / "bin" / "java"
        if candidate.is_file():
            return str(candidate)
    return resolve_executable("java")


class RewriteInventoryTool:
    def is_available(self) -> bool:
        return settings.rewrite_test_inventory_jar_path.is_file() and resolve_java_executable() is not None

    def scan(self, project_dir: Path) -> ProjectInventory:
        """Run the OpenRewrite LST scan over ``project_dir`` and return the parsed inventory."""
        java = self._require_java()
        jar = self._require_jar()

        with tempfile.TemporaryDirectory(prefix="rewrite-inventory-") as tmp:
            output_path = Path(tmp) / "inventory.json"
            command = [java, "-jar", str(jar), "inventory", str(project_dir), str(output_path)]
            result = run_command(
                command,
                timeout=settings.unit_test_timeout_seconds,
                env=build_tool_env(MIN_JAVA_MAJOR),
            )
            if not output_path.is_file():
                tail = (result.stderr or result.stdout or "").strip().splitlines()[-10:]
                raise UnitTestToolUnavailableError(
                    "OpenRewrite test inventory scan failed to produce output: "
                    + (" | ".join(tail) if tail else "no output.")
                )
            data = json.loads(output_path.read_text(encoding="utf-8"))

        inventory = ProjectInventory.from_dict(data)
        if inventory.parse_errors:
            logger.warning(
                "OpenRewrite inventory scan for %s had %d parse error(s)",
                project_dir, len(inventory.parse_errors),
            )
        return inventory

    # -- resolution ----------------------------------------------------------- #

    def _require_java(self) -> str:
        java = resolve_java_executable()
        if not java:
            raise UnitTestToolUnavailableError(
                f"No JDK {MIN_JAVA_MAJOR}+ was found to run the OpenRewrite test-inventory tool."
            )
        return java

    def _require_jar(self) -> Path:
        jar = settings.rewrite_test_inventory_jar_path
        if not jar.is_file():
            raise UnitTestToolUnavailableError(
                "The OpenRewrite test-inventory tool has not been built. Run "
                "`mvn -f tools/rewrite-test-inventory/pom.xml package` once, then retry."
            )
        return jar
