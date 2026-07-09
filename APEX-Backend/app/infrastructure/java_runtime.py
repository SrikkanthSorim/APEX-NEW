"""Java runtime environment helpers for external build tools."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


def build_tool_env() -> dict[str, str]:
    """Return an environment for Maven/Gradle using the configured JDK."""
    env = os.environ.copy()
    java_home = (settings.build_java_home or "").strip()
    if not java_home:
        return env

    java_home_path = Path(java_home)
    java_executable = java_home_path / "bin" / ("java.exe" if os.name == "nt" else "java")
    if not java_executable.is_file():
        logger.warning("Configured BUILD_JAVA_HOME does not contain a Java executable: %s", java_home)
        return env

    env["JAVA_HOME"] = str(java_home_path)
    env["PATH"] = f"{java_home_path / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env
