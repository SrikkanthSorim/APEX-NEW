"""Semantic chunking of a repository's discovery report.

The discovery report (``discovery-report.json``) is split into a handful of
human-readable knowledge sections — one chunk per ``chunk_type`` — instead of
being embedded as raw JSON. Natural-language sentences embed far better than
JSON braces/keys, so retrieval quality is much higher and each retrieved chunk
is directly usable as grounded LLM context.

Kept pure: input is the report ``dict``, output is a list of
:class:`KnowledgeChunk` objects. No embedding, storage, or IO here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class KnowledgeChunk:
    """A single semantic section of repository knowledge, ready to embed."""

    chunk_type: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _clean(value: Any, fallback: str = "unknown") -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _yes_no(value: Any) -> str:
    return "yes" if bool(value) else "no"


def build_chunks(report: dict[str, Any]) -> list[KnowledgeChunk]:
    """Split a discovery report into semantic knowledge chunks.

    Empty/irrelevant sections are skipped so we never embed noise. The order
    roughly follows how a reader would explore the project.
    """
    repo_name = _clean(report.get("repoName"), "the repository")
    build_tool = _clean(report.get("buildTool"))
    java_version = _clean(report.get("currentJavaVersion"))
    spring_boot = report.get("springBootVersion")
    project_type = _clean(report.get("projectType"))
    frameworks = [str(f).strip() for f in (report.get("frameworks") or []) if str(f).strip()]
    dependencies = [d for d in (report.get("dependencies") or []) if isinstance(d, dict)]
    build_plugins = [p for p in (report.get("buildPlugins") or []) if isinstance(p, dict)]
    modules = [str(m).strip() for m in (report.get("modules") or []) if str(m).strip()]
    multi_module = bool(report.get("multiModule"))
    frontend = report.get("frontend") or {}
    detected_files = report.get("detectedFiles") or {}

    chunks: list[KnowledgeChunk] = []

    # --- Project information ------------------------------------------------ #
    project_lines = [
        f"Repository: {repo_name}.",
        f"Owner: {_clean(report.get('owner'))}.",
        f"Repository URL: {_clean(report.get('repoUrl'))}.",
        f"Project type: {project_type}.",
        f"Multi-module project: {_yes_no(multi_module)}.",
    ]
    if modules:
        project_lines.append(f"Modules ({len(modules)}): {', '.join(modules)}.")
    chunks.append(KnowledgeChunk("project_info", " ".join(project_lines)))

    # --- Java information --------------------------------------------------- #
    java_text = (
        f"The project's current/detected Java version is Java {java_version}. "
        f"This is the source Java version considered for migration and modernization."
    )
    chunks.append(KnowledgeChunk("java_info", java_text))

    # --- Build tool --------------------------------------------------------- #
    build_lines = [f"The project is built with {build_tool}."]
    if build_plugins:
        plugin_parts = []
        for plugin in build_plugins:
            name = _clean(plugin.get("id"))
            version = plugin.get("version")
            plugin_parts.append(f"{name} (version {version})" if version else name)
        build_lines.append(f"Build plugins configured: {', '.join(plugin_parts)}.")
    chunks.append(KnowledgeChunk("build_tool", " ".join(build_lines)))

    # --- Framework information ---------------------------------------------- #
    framework_lines = []
    if spring_boot:
        framework_lines.append(f"Spring Boot version {spring_boot} is used.")
    if frameworks:
        framework_lines.append(f"Detected frameworks and libraries: {', '.join(frameworks)}.")
    if not framework_lines:
        framework_lines.append("No specific application framework was detected.")
    chunks.append(KnowledgeChunk("framework_info", " ".join(framework_lines)))

    # --- Dependencies ------------------------------------------------------- #
    dep_count = report.get("dependencyCount", len(dependencies))
    if dependencies:
        dep_lines = [f"The project declares {dep_count} dependencies:"]
        for dep in dependencies:
            group = _clean(dep.get("groupId"), "")
            artifact = _clean(dep.get("artifactId"), "unknown")
            version = dep.get("version")
            coord = f"{group}:{artifact}" if group else artifact
            dep_lines.append(f"- {coord}{f' version {version}' if version else ' (version managed)'}")
        chunks.append(KnowledgeChunk("dependencies", "\n".join(dep_lines)))
    else:
        chunks.append(
            KnowledgeChunk("dependencies", "No third-party dependencies were detected.")
        )

    # --- Frontend ----------------------------------------------------------- #
    if frontend.get("detected"):
        frontend_text = (
            f"A frontend was detected: type {_clean(frontend.get('type'))}, "
            f"located at {_clean(frontend.get('path'))}, "
            f"package manager {_clean(frontend.get('packageManager'))}."
        )
    else:
        frontend_text = "No frontend was detected; this is a backend/Java-only project."
    chunks.append(KnowledgeChunk("frontend", frontend_text))

    # --- Detected build files ---------------------------------------------- #
    present = [name for name, ok in detected_files.items() if ok]
    files_text = (
        f"Detected build/config files: {', '.join(present)}."
        if present
        else "No standard build/config files were detected."
    )
    chunks.append(KnowledgeChunk("detected_files", files_text))

    return chunks
