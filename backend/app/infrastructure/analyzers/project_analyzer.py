"""Coordinates all Discovery detectors over a cloned project.

Reads the root build files once (parsing ``pom.xml`` a single time), then
delegates each concern to its dedicated detector and assembles a
:class:`ProjectAnalysis`. Strictly read-only — nothing here modifies the repo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.etree.ElementTree import Element, ParseError, fromstring

from app.infrastructure.analyzers.build_tool_detector import BuildToolDetector
from app.infrastructure.analyzers.dependency_analyzer import Dependency, DependencyAnalyzer
from app.infrastructure.analyzers.frontend_detector import FrontendDetector, FrontendResult
from app.infrastructure.analyzers.java_version_detector import JavaVersionDetector
from app.infrastructure.analyzers.module_detector import ModuleDetector
from app.infrastructure.analyzers.project_type_detector import ProjectTypeDetector
from app.infrastructure.analyzers.spring_boot_detector import SpringBootDetector
from app.shared import file_utils


@dataclass(frozen=True)
class ProjectAnalysis:
    build_tool: str
    primary_build_tool: str | None
    build_warning: str | None
    current_java_version: str
    spring_boot_version: str | None
    project_type: str
    multi_module: bool
    modules: list[str]
    dependencies: list[Dependency]
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
        self._dependencies = DependencyAnalyzer()
        self._modules = ModuleDetector()
        self._project_type = ProjectTypeDetector()
        self._frontend = FrontendDetector()

    def analyze(self, root: Path) -> ProjectAnalysis:
        build_tool = self._build_tool.detect(root)

        pom_root = self._parse_pom(root / "pom.xml") if build_tool.has_pom_xml else None
        build_gradle_text = self._read_gradle_build(root)
        settings_gradle_text = self._read_first(
            root, "settings.gradle", "settings.gradle.kts"
        )
        gradle_properties_text = self._read_first(root, "gradle.properties")

        java_version = self._java_version.detect(
            build_tool.build_tool, pom_root, build_gradle_text, gradle_properties_text
        )
        spring_boot_version = self._spring_boot.detect(pom_root, build_gradle_text)
        dependencies = self._dependencies.analyze(pom_root, build_gradle_text)
        modules = self._modules.detect(pom_root, settings_gradle_text)
        project_type = self._project_type.detect(
            root, build_tool.is_supported, spring_boot_version, dependencies
        )
        frontend = self._frontend.detect(root)

        has_src_main = file_utils.exists(root, "src", "main")
        has_src_test = file_utils.exists(root, "src", "test")

        return ProjectAnalysis(
            build_tool=build_tool.build_tool,
            primary_build_tool=build_tool.primary_build_tool,
            build_warning=build_tool.warning,
            current_java_version=java_version,
            spring_boot_version=spring_boot_version,
            project_type=project_type,
            multi_module=modules.multi_module,
            modules=modules.modules,
            dependencies=dependencies,
            frontend=frontend,
            has_pom_xml=build_tool.has_pom_xml,
            has_build_gradle=build_tool.has_build_gradle,
            has_build_gradle_kts=build_tool.has_build_gradle_kts,
            has_package_json=(root / "package.json").is_file(),
            has_src_main=has_src_main,
            has_src_test=has_src_test,
            has_tests=has_src_test,
            java_files=file_utils.find_files(root, ".java"),
        )

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
