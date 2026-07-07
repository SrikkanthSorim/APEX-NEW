"""Detects single- vs multi-module layout and lists module names."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element


@dataclass(frozen=True)
class ModuleResult:
    multi_module: bool
    modules: list[str] = field(default_factory=list)


class ModuleDetector:
    def detect(
        self,
        pom_root: Element | None,
        settings_gradle_text: str,
    ) -> ModuleResult:
        if pom_root is not None:
            modules = self._from_maven(pom_root)
            if modules:
                return ModuleResult(multi_module=True, modules=modules)
        if settings_gradle_text:
            modules = self._from_gradle(settings_gradle_text)
            if modules:
                return ModuleResult(multi_module=True, modules=modules)
        return ModuleResult(multi_module=False, modules=[])

    # -- Maven --------------------------------------------------------------- #

    def _from_maven(self, pom_root: Element) -> list[str]:
        block = pom_root.find("modules")
        if block is None:
            return []
        return [m.text.strip() for m in block.findall("module") if m.text and m.text.strip()]

    # -- Gradle -------------------------------------------------------------- #

    def _from_gradle(self, settings_text: str) -> list[str]:
        modules: list[str] = []
        # include 'a', 'b'  |  include(":a", ":b")  |  include ':a:b'
        for match in re.finditer(r"include\s*\(?\s*(.+)", settings_text):
            fragment = match.group(1)
            for name in re.findall(r"['\"]:?([\w.\-:]+)['\"]", fragment):
                cleaned = name.strip().lstrip(":")
                if cleaned and cleaned not in modules:
                    modules.append(cleaned)
        return modules
