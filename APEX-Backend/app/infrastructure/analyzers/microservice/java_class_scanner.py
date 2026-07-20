"""Lightweight static scan of ``.java`` source files.

Not a full Java parser — a pragmatic regex-based scan (package, class name,
Spring/JPA annotations, superclass/interfaces, injected field/constructor
dependency types, REST mapping endpoints) that is accurate enough to drive the
Microservice Eligibility Assessment's chunking and scoring. Every value here
comes directly from the repository's real source text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.shared import file_utils

# Test sources aren't part of the application's business architecture.
_TEST_DIR_PARTS = {"test", "tests", "androidTest"}

_PACKAGE_RE = re.compile(r"(?m)^\s*package\s+([\w.]+)\s*;")
_TYPE_DECL_RE = re.compile(r"\b(?:class|interface|enum|record)\s+(\w+)")
_ANNOTATION_TOKENS = (
    "RestController",
    "Controller",
    "Service",
    "Repository",
    "Entity",
    "Document",
    "Component",
)
_EXTENDS_RE = re.compile(r"\bextends\s+([\w][\w.]*)\s*(<[^{]*?>)?\s*(?:implements\b|\{)")
_IMPLEMENTS_RE = re.compile(r"\bimplements\s+([\w,\s.<>]+?)\s*\{")
_MAPPING_RE = re.compile(
    r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\s*(\(([^)]*)\))?"
)
_QUOTED_RE = re.compile(r'"([^"]*)"')
_FIELD_DEP_RE = re.compile(
    r"(?:private|protected|public)\s+(?:final\s+)?([A-Z]\w*)(?:<[\w,\s<>]*>)?\s+\w+\s*[=;]"
)
_GENERIC_BASE_RE = re.compile(r"^([\w.]+)")


@dataclass(frozen=True)
class JavaEndpoint:
    method: str
    path: str


@dataclass
class JavaClassInfo:
    relative_path: str
    package: str
    class_name: str
    annotations: set[str] = field(default_factory=set)
    extends: str | None = None
    implements: list[str] = field(default_factory=list)
    dependencies: set[str] = field(default_factory=set)
    endpoints: list[JavaEndpoint] = field(default_factory=list)


class JavaClassScanner:
    """Scans every non-test ``.java`` file under a repo root into :class:`JavaClassInfo`."""

    def scan(self, root: Path) -> list[JavaClassInfo]:
        results: list[JavaClassInfo] = []
        for relative_path in file_utils.find_files(root, ".java"):
            parts = Path(relative_path).parts
            if any(part in _TEST_DIR_PARTS for part in parts):
                continue

            text = file_utils.read_text(root / relative_path)
            if not text.strip():
                continue

            info = self._parse(relative_path, text)
            if info is not None:
                results.append(info)
        return results

    @staticmethod
    def _parse(relative_path: str, text: str) -> JavaClassInfo | None:
        package_match = _PACKAGE_RE.search(text)
        package = package_match.group(1) if package_match else ""

        file_stem = Path(relative_path).stem
        class_name = file_stem
        # Prefer the type declaration matching the filename (standard Java
        # convention); fall back to the first declared type otherwise.
        if not re.search(rf"\b(?:class|interface|enum|record)\s+{re.escape(file_stem)}\b", text):
            fallback = _TYPE_DECL_RE.search(text)
            if fallback:
                class_name = fallback.group(1)

        annotations = {token for token in _ANNOTATION_TOKENS if re.search(rf"@{token}\b", text)}

        extends_match = _EXTENDS_RE.search(text)
        extends = None
        extends_generic_args: list[str] = []
        if extends_match:
            base = _GENERIC_BASE_RE.match(extends_match.group(1).strip())
            extends = base.group(1).rsplit(".", 1)[-1] if base else None
            generics_raw = (extends_match.group(2) or "").strip("<>")
            for part in generics_raw.split(","):
                part = part.strip().split("<")[0].strip()
                if part and part[0].isupper():
                    extends_generic_args.append(part.rsplit(".", 1)[-1])

        implements: list[str] = []
        implements_match = _IMPLEMENTS_RE.search(text)
        if implements_match:
            for raw in implements_match.group(1).split(","):
                base = _GENERIC_BASE_RE.match(raw.strip())
                if base:
                    implements.append(base.group(1).rsplit(".", 1)[-1])

        endpoints: list[JavaEndpoint] = []
        if "Controller" in annotations or "RestController" in annotations:
            for method, _, args in _MAPPING_RE.findall(text):
                path_match = _QUOTED_RE.search(args)
                endpoints.append(JavaEndpoint(method=method, path=path_match.group(1) if path_match else ""))

        dependencies = {
            match for match in _FIELD_DEP_RE.findall(text) if match != class_name
        }
        # Constructor-parameter injection (works even without Lombok's `final`
        # field pattern above).
        ctor_match = re.search(rf"\b{re.escape(class_name)}\s*\(([^)]*)\)\s*\{{", text)
        if ctor_match:
            for param in ctor_match.group(1).split(","):
                param = param.strip()
                type_match = re.match(r"([A-Z]\w*)(?:<[\w,\s<>]*>)?\s+\w+$", param)
                if type_match and type_match.group(1) != class_name:
                    dependencies.add(type_match.group(1))
        # Repository interfaces (e.g. `JpaRepository<Owner, Integer>`) don't
        # have fields — the entity they manage only appears as a generic type
        # argument on the `extends` clause, so surface it as a dependency too.
        dependencies.update(arg for arg in extends_generic_args if arg != class_name)

        return JavaClassInfo(
            relative_path=relative_path,
            package=package,
            class_name=class_name,
            annotations=annotations,
            extends=extends,
            implements=implements,
            dependencies=dependencies,
            endpoints=endpoints,
        )
