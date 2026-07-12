"""Java runtime environment helpers for external build tools.

Multiple JDKs are commonly installed side by side on a dev/CI machine (e.g.
JDK 8, 11, 17, 21 under ``C:\\Program Files\\Java``) while a single ambient
``JAVA_HOME``/``PATH`` only points at one of them. Rather than always using
whatever the ambient environment happens to resolve to, this module can
discover the other installed JDKs and pick the one that actually matches the
selected migration target, so OpenRewrite and the build-validation step run
under a JDK capable of the requested ``--release``.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.shared.command_runner import resolve_executable, run_command

logger = logging.getLogger(__name__)

# Directories commonly used by JDK installers/IDEs. Each immediate child
# directory is treated as a candidate JDK home.
_WINDOWS_JDK_SEARCH_ROOTS = (
    r"C:\Program Files\Java",
    r"C:\Program Files\Eclipse Adoptium",
    r"C:\Program Files\Microsoft",
    r"C:\Program Files\AdoptOpenJDK",
    r"C:\Program Files\Amazon Corretto",
    r"C:\Program Files\Zulu",
)
_POSIX_JDK_SEARCH_ROOTS = (
    "/usr/lib/jvm",
    "/opt/java",
)

_JAVA_HOME_ENV_PATTERN = re.compile(r"^JAVA_HOME(_\d+)?(_X\d+)?$", re.IGNORECASE)


@dataclass(frozen=True)
class JavaRuntimeInfo:
    executable: str | None
    java_home: str | None
    version_text: str
    major_version: int | None


def build_tool_env(target_major: int | None = None) -> dict[str, str]:
    """Return an environment for Maven/Gradle subprocesses.

    When ``target_major`` is given, prefers an installed JDK that can satisfy
    that release (closest match at or above it) over the ambient/configured
    default, so the subprocess actually compiles at the requested level.
    """
    env = os.environ.copy()
    tool_dirs: list[Path] = []

    java_home: str | None = None
    if target_major is not None:
        selected = _select_jdk_for_target(target_major)
        if selected and selected.java_home:
            java_home = selected.java_home
    if not java_home:
        java_home = (settings.build_java_home or "").strip() or None
    if not java_home:
        env["PATH"] = _prepend_tool_dirs(env.get("PATH", ""), *tool_dirs)
        return env

    java_home_path = Path(java_home)
    java_executable = java_home_path / "bin" / ("java.exe" if os.name == "nt" else "java")
    if not java_executable.is_file():
        logger.warning("Configured/selected JAVA_HOME does not contain a Java executable: %s", java_home)
        env["PATH"] = _prepend_tool_dirs(env.get("PATH", ""), *tool_dirs)
        return env

    tool_dirs.append(java_home_path / "bin")
    env["JAVA_HOME"] = str(java_home_path)
    env["PATH"] = _prepend_tool_dirs(env.get("PATH", ""), *tool_dirs)
    return env


def resolve_gradle_executable(project_dir: Path) -> str | None:
    """Resolve Gradle from wrapper, GRADLE_HOME, or ambient PATH."""
    wrapper = project_dir / ("gradlew.bat" if os.name == "nt" else "gradlew")
    if wrapper.is_file():
        return str(wrapper)

    gradle_home = (settings.gradle_home or "").strip()
    if gradle_home:
        gradle_executable = Path(gradle_home) / "bin" / ("gradle.bat" if os.name == "nt" else "gradle")
        if gradle_executable.is_file():
            return str(gradle_executable)
        logger.warning("Configured GRADLE_HOME does not contain a Gradle executable: %s", gradle_home)

    return resolve_executable("gradle")


def build_java_runtime() -> JavaRuntimeInfo:
    """Detect the JDK Maven/Gradle subprocesses use by default (no target)."""
    java_home = (settings.build_java_home or "").strip() or None
    executable = _configured_java_executable(java_home) or resolve_executable("java")
    if not executable:
        return JavaRuntimeInfo(
            executable=None,
            java_home=java_home,
            version_text="Java runtime not found",
            major_version=None,
        )

    result = run_command([executable, "-version"], timeout=10, env=build_tool_env())
    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    version_text = output.splitlines()[0] if output else "Java version unavailable"
    return JavaRuntimeInfo(
        executable=executable,
        java_home=java_home,
        version_text=version_text,
        major_version=_parse_runtime_major(output),
    )


def build_compatible_java_target(target_java_version: str | None) -> tuple[str | None, str | None]:
    """Return the user-selected target Java version, unchanged.

    The migration always targets exactly what the user selected — the platform
    never silently downgrades it to match whatever JDK happens to be
    installed. If a locally installed JDK can satisfy the target (even if it
    isn't the ambient default), the OpenRewrite run and build validation use
    that JDK automatically (see :func:`build_tool_env`). Only when *no*
    installed JDK can satisfy the target does this return an informational
    message; the migration target itself is never changed.
    """
    requested = _parse_major(target_java_version)
    if requested is None:
        return target_java_version, None

    selected = _select_jdk_for_target(requested)
    if selected is None or selected.major_version is None or selected.major_version < requested:
        closest = selected.version_text if selected else "no JDK found"
        message = (
            f"Target Java {requested} selected, but no local JDK {requested}+ "
            f"was found (closest available: {closest}). OpenRewrite/build "
            f"validation may fail to compile at this release. The migrated "
            f"project's build configuration still targets Java {requested} as "
            f"selected; install a JDK {requested}+ locally (or set "
            f"BUILD_JAVA_HOME) to validate the build on this machine."
        )
        return str(requested), message
    return str(requested), None


def max_available_java_major() -> int | None:
    """Highest Java major version available from any discovered/configured JDK."""
    candidates = list(_discover_jdks())
    default_runtime = build_java_runtime()
    if default_runtime.major_version is not None:
        candidates.append(default_runtime)
    majors = [c.major_version for c in candidates if c.major_version is not None]
    return max(majors) if majors else None


# -- JDK discovery ------------------------------------------------------------ #


def _select_jdk_for_target(target_major: int) -> JavaRuntimeInfo | None:
    """Pick the installed JDK best suited to compile at ``target_major``.

    Prefers the closest JDK at or above the target (a JDK can compile to any
    older ``--release`` but not a newer one). Falls back to the newest
    available JDK when none meets the target.
    """
    candidates = list(_discover_jdks())
    default_runtime = build_java_runtime()
    if default_runtime.major_version is not None:
        candidates.append(default_runtime)
    if not candidates:
        return None

    eligible = [c for c in candidates if c.major_version is not None and c.major_version >= target_major]
    if eligible:
        return min(eligible, key=lambda c: c.major_version)
    return max(candidates, key=lambda c: c.major_version or 0)


def _discover_jdks() -> list[JavaRuntimeInfo]:
    found: dict[int, JavaRuntimeInfo] = {}
    for directory in _candidate_jdk_dirs():
        java_executable = directory / "bin" / ("java.exe" if os.name == "nt" else "java")
        if not java_executable.is_file():
            continue
        major = _infer_major_from_name(directory.name)
        if major is None or major in found:
            continue
        found[major] = JavaRuntimeInfo(
            executable=str(java_executable),
            java_home=str(directory),
            version_text=f"JDK {major} ({directory})",
            major_version=major,
        )
    return list(found.values())


def _candidate_jdk_dirs() -> list[Path]:
    roots = list(_WINDOWS_JDK_SEARCH_ROOTS if os.name == "nt" else _POSIX_JDK_SEARCH_ROOTS)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        roots.append(str(Path(local_app_data) / "Programs" / "Microsoft"))
    user_profile = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if user_profile:
        roots.append(str(Path(user_profile) / ".jdks"))

    dirs: list[Path] = []
    for root in roots:
        root_path = Path(root)
        if not root_path.is_dir():
            continue
        try:
            children = [child for child in root_path.iterdir() if child.is_dir()]
        except OSError:
            continue
        dirs.extend(children)

    # Per-version env vars some CI runners set (JAVA_HOME_17_X64, JDK_21, ...).
    for key, value in os.environ.items():
        if _JAVA_HOME_ENV_PATTERN.match(key) and value:
            path = Path(value)
            if path.is_dir():
                dirs.append(path)

    configured = (settings.build_java_home or "").strip()
    if configured and Path(configured).is_dir():
        dirs.append(Path(configured))

    return dirs


def _infer_major_from_name(name: str) -> int | None:
    """Best-effort major-version guess from a JDK directory name.

    Handles both modern (``jdk-21.0.10``, ``jdk-17``) and legacy
    (``jdk1.8.0_482``, ``corretto-1.8.0_482``, ``jre1.8.0_491``) naming.
    """
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", name)
    if not match:
        return None
    first = int(match.group(1))
    if first == 1 and match.group(2) and match.group(2).isdigit():
        return int(match.group(2))
    return first


def _configured_java_executable(java_home: str | None) -> str | None:
    if not java_home:
        return None
    java_home_path = Path(java_home)
    java_executable = java_home_path / "bin" / ("java.exe" if os.name == "nt" else "java")
    return str(java_executable) if java_executable.is_file() else None


def _prepend_tool_dirs(path_value: str, *tool_dirs: Path) -> str:
    parts = [str(path) for path in tool_dirs if path.is_dir()]
    gradle_home = (settings.gradle_home or "").strip()
    if gradle_home:
        gradle_bin = Path(gradle_home) / "bin"
        if gradle_bin.is_dir():
            parts.append(str(gradle_bin))
    parts.append(path_value)
    return os.pathsep.join(part for part in parts if part)


def _parse_major(version: str | None) -> int | None:
    if not version:
        return None
    text = version.strip().lower().replace("java", "").strip()
    if text.startswith("1."):
        text = text.split(".", 1)[1]
    text = text.split(".", 1)[0]
    return int(text) if text.isdigit() else None


def _parse_runtime_major(output: str) -> int | None:
    match = re.search(r'version\s+"([^"]+)"', output or "")
    if not match:
        match = re.search(r"\b(?:openjdk|java)\s+(\d+(?:\.\d+)*)", (output or "").lower())
    version = match.group(1) if match else ""
    return _parse_major(version)
