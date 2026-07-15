"""Coordinates all Discovery detectors over a cloned project.

Reads the root build files once (parsing ``pom.xml`` a single time), then
delegates each concern to its dedicated detector and assembles a
:class:`ProjectAnalysis`. Strictly read-only — nothing here modifies the repo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.etree.ElementTree import Element, ParseError, fromstring

from app.infrastructure.analyzers.build_metadata_analyzer import (
    BomVersion,
    BuildMetadataAnalyzer,
    BuildPlugin,
)
from app.infrastructure.analyzers.build_tool_detector import BuildToolDetector
from app.infrastructure.analyzers.dependency_analyzer import Dependency, DependencyAnalyzer
from app.infrastructure.analyzers.frontend_detector import FrontendDetector, FrontendResult
from app.infrastructure.analyzers.java_version_detector import JavaVersionDetector
from app.infrastructure.analyzers.module_detector import ModuleDetector
from app.infrastructure.analyzers.project_type_detector import ProjectTypeDetector
from app.infrastructure.analyzers.spring_boot_detector import SpringBootDetector
from app.infrastructure.analyzers.spring_entrypoint_scanner import SpringEntrypointScanner
from app.infrastructure.analyzers.spring_framework_detector import SpringFrameworkDetector
from app.shared import file_utils


@dataclass(frozen=True)
class ProjectAnalysis:
    build_tool: str
    primary_build_tool: str | None
    build_warning: str | None
    current_java_version: str
    spring_boot_version: str | None
    spring_framework_version: str | None
    spring_boot_signal: bool
    spring_entry_class: str | None
    project_type: str
    multi_module: bool
    modules: list[str]
    dependencies: list[Dependency]
    build_plugins: list[BuildPlugin]
    bom_versions: list[BomVersion]
    frameworks: list[str]
    frontend: FrontendResult
    has_pom_xml: bool
    has_build_gradle: bool
    has_build_gradle_kts: bool
    has_package_json: bool
    has_src_main: bool
    has_src_test: bool
    has_tests: bool
    java_files: list[str] = field(default_factory=list)

    @property
    def dependency_count(self) -> int:
        return len(self.dependencies)

    @property
    def is_supported(self) -> bool:
        return self.build_tool in ("MAVEN", "GRADLE")


class ProjectAnalyzer:
    """Runs every detector over the cloned repository root."""

    def __init__(self) -> None:
        self._build_tool = BuildToolDetector()
        self._java_version = JavaVersionDetector()
        self._spring_boot = SpringBootDetector()
        self._spring_framework = SpringFrameworkDetector()
        self._spring_entrypoint = SpringEntrypointScanner()
        self._dependencies = DependencyAnalyzer()
        self._metadata = BuildMetadataAnalyzer()
        self._modules = ModuleDetector()
        self._project_type = ProjectTypeDetector()
        self._frontend = FrontendDetector()

    def analyze(self, root: Path) -> ProjectAnalysis:
        # The Java project may live in a subfolder (e.g. backend/pom.xml) rather
        # than the repo root. Resolve the actual project directory and analyze
        # from there; the frontend is still detected across the whole repo.
        project_root = self._resolve_project_root(root)

        build_tool = self._build_tool.detect(project_root)

        pom_root = (
            self._parse_pom(project_root / "pom.xml") if build_tool.has_pom_xml else None
        )
        build_gradle_text = self._read_gradle_build(project_root)
        settings_gradle_text = self._read_first(
            project_root, "settings.gradle", "settings.gradle.kts"
        )
        gradle_properties_text = self._read_first(project_root, "gradle.properties")

        java_version = self._java_version.detect(
            build_tool.build_tool, pom_root, build_gradle_text, gradle_properties_text
        )
        spring_boot_version = self._spring_boot.detect(pom_root, build_gradle_text)
        spring_boot_signal = self._spring_boot.has_signal(pom_root, build_gradle_text)
        spring_framework_version = self._spring_framework.detect(pom_root, build_gradle_text)
        java_files = file_utils.find_files(project_root, ".java")

        spring_entry_class: str | None = None
        if not spring_boot_version and not spring_boot_signal:
            # Build-file signals were inconclusive (e.g. a custom parent that
            # manages the Spring Boot version elsewhere) -- fall back to a
            # real code-level scan for the entry-point markers.
            entrypoint = self._spring_entrypoint.scan(project_root, java_files)
            if entrypoint.found:
                spring_boot_signal = True
                spring_entry_class = entrypoint.entry_class

        dependencies = self._dependencies.analyze(pom_root, build_gradle_text)
        build_plugins = self._metadata.detect_plugins(pom_root, build_gradle_text)
        bom_versions = self._metadata.detect_boms(pom_root, build_gradle_text)
        frameworks = self._metadata.detect_frameworks(
            spring_boot_version=spring_boot_version,
            dependencies=dependencies,
            build_gradle_text=build_gradle_text,
            spring_boot_signal=spring_boot_signal,
        )
        modules = self._modules.detect(pom_root, settings_gradle_text)
        project_type = self._project_type.detect(
            project_root,
            build_tool.is_supported,
            spring_boot_version,
            dependencies,
            spring_boot_signal=spring_boot_signal,
        )
        # Scan the whole repo for a frontend (it commonly sits beside the backend,
        # e.g. repo/frontend + repo/backend).
        frontend = self._frontend.detect(root)

        has_src_main = file_utils.exists(project_root, "src", "main")
        has_src_test = file_utils.exists(project_root, "src", "test")

        return ProjectAnalysis(
            build_tool=build_tool.build_tool,
            primary_build_tool=build_tool.primary_build_tool,
            build_warning=build_tool.warning,
            current_java_version=java_version,
            spring_boot_version=spring_boot_version,
            spring_framework_version=spring_framework_version,
            spring_boot_signal=spring_boot_signal,
            spring_entry_class=spring_entry_class,
            project_type=project_type,
            multi_module=modules.multi_module,
            modules=modules.modules,
            dependencies=dependencies,
            build_plugins=build_plugins,
            bom_versions=bom_versions,
            frameworks=frameworks,
            frontend=frontend,
            has_pom_xml=build_tool.has_pom_xml,
            has_build_gradle=build_tool.has_build_gradle,
            has_build_gradle_kts=build_tool.has_build_gradle_kts,
            has_package_json=(root / "package.json").is_file() or frontend.detected,
            has_src_main=has_src_main,
            has_src_test=has_src_test,
            has_tests=has_src_test,
            java_files=java_files,
        )

    @staticmethod
    def _resolve_project_root(root: Path) -> Path:
        """Return the directory that holds the build file.

        Prefers the repo root when it already has a build file; otherwise finds
        the shallowest subfolder containing a ``pom.xml`` / ``build.gradle`` /
        ``build.gradle.kts``. Falls back to the repo root when none is found.
        """
        build_files = ("pom.xml", "build.gradle", "build.gradle.kts")
        if any((root / name).is_file() for name in build_files):
            return root
        found = file_utils.find_shallowest_dir_with(root, build_files)
        return found or root

    # -- file reading -------------------------------------------------------- #

    @staticmethod
    def _parse_pom(pom_path: Path) -> Element | None:
        text = file_utils.read_text(pom_path)
        if not text.strip():
            return None
        try:
            root = fromstring(text)
        except ParseError:
            return None
        # Strip XML namespaces so downstream detectors can query bare tag names.
        for element in root.iter():
            if isinstance(element.tag, str) and "}" in element.tag:
                element.tag = element.tag.split("}", 1)[1]
        return root

    @staticmethod
    def _read_gradle_build(root: Path) -> str:
        parts = [
            file_utils.read_text(root / name)
            for name in ("build.gradle", "build.gradle.kts")
            if (root / name).is_file()
        ]
        return "\n".join(parts)

    @staticmethod
    def _read_first(root: Path, *names: str) -> str:
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return file_utils.read_text(candidate)
        return ""
