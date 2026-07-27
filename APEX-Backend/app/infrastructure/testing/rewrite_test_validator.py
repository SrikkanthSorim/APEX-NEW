"""Validates an LLM-generated unit test candidate before it is ever written
into a repository (Step 6 of the unit-test generation pipeline).

Flow: LLM JSON -> JSON schema -> package/class name -> target production
method exists -> parse with the real OpenRewrite Java parser (via the
``rewrite-test-inventory`` CLI's ``validate`` mode) -> duplicate class/method
check. Nothing here trusts the raw LLM response directly; every check must
pass before ``GenerateUnitTestsUseCase`` writes the file to disk.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import UnitTestToolUnavailableError
from app.domain.models.unit_test_report import ClassInventoryEntry
from app.infrastructure.java_runtime import build_tool_env
from app.infrastructure.testing.rewrite_inventory_tool import MIN_JAVA_MAJOR, resolve_java_executable
from app.shared.command_runner import run_command

REQUIRED_RESPONSE_KEYS = ("testClassName", "packageName", "targetPath", "framework", "testCases", "sourceCode")
REQUIRED_TEST_CASE_KEYS = ("methodName", "type", "targetMethod", "scenario", "expectedResult")

# Rejected per the spec's "do not generate" list -- checked textually against
# the LLM's own source since these are unambiguous anti-patterns regardless
# of surrounding code.
_FORBIDDEN_PATTERNS = (
    "assertTrue(true)",
    "assertFalse(false)",
)


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    class_name: str | None = None
    package_name: str | None = None
    imports: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class RewriteTestValidator:
    def validate_schema(self, response: dict) -> list[str]:
        """Step 1: strict JSON schema validation of the raw LLM response."""
        errors = []
        if not isinstance(response, dict):
            return ["LLM response was not a JSON object."]
        for key in REQUIRED_RESPONSE_KEYS:
            if key not in response:
                errors.append(f"Missing required field '{key}'.")
        test_cases = response.get("testCases")
        if not isinstance(test_cases, list) or not test_cases:
            errors.append("'testCases' must be a non-empty array.")
        else:
            for i, case in enumerate(test_cases):
                if not isinstance(case, dict):
                    errors.append(f"testCases[{i}] is not an object.")
                    continue
                for key in REQUIRED_TEST_CASE_KEYS:
                    if key not in case:
                        errors.append(f"testCases[{i}] missing required field '{key}'.")
        source_code = response.get("sourceCode")
        if not isinstance(source_code, str) or not source_code.strip():
            errors.append("'sourceCode' must be a non-empty string.")
        return errors

    def validate(
        self,
        response: dict,
        *,
        class_entry: ClassInventoryEntry,
        existing_test_class_names: set[str],
    ) -> ValidationResult:
        schema_errors = self.validate_schema(response)
        if schema_errors:
            return ValidationResult(valid=False, errors=schema_errors)

        expected_class = str(response["testClassName"])
        expected_package = str(response["packageName"])
        target_path = str(response["targetPath"]).replace("\\", "/")
        source_code = str(response["sourceCode"])

        errors: list[str] = []

        for pattern in _FORBIDDEN_PATTERNS:
            if pattern in source_code:
                errors.append(f"Generated source contains a disallowed placeholder assertion: {pattern}")

        if expected_class in existing_test_class_names:
            errors.append(f"Duplicate test class '{expected_class}' already exists in the project.")

        if expected_package != class_entry.package_name:
            errors.append(
                f"Test package '{expected_package}' does not match production class package "
                f"'{class_entry.package_name}'."
            )

        production_method_names = {m.name for m in class_entry.methods}
        target_methods = {
            str(case.get("targetMethod")) for case in response.get("testCases", []) if isinstance(case, dict)
        }
        unknown_targets = target_methods - production_method_names
        if unknown_targets:
            errors.append(
                f"testCases reference method(s) not found on {class_entry.class_name}: "
                f"{', '.join(sorted(unknown_targets))}."
            )

        method_names = [
            str(case.get("methodName")) for case in response.get("testCases", []) if isinstance(case, dict)
        ]
        duplicates = {name for name in method_names if method_names.count(name) > 1}
        if duplicates:
            errors.append(f"Duplicate test method name(s) within the generated class: {', '.join(sorted(duplicates))}.")

        parsed = self._parse_source(source_code)
        if not parsed.get("valid"):
            errors.extend(parsed.get("parseErrors") or ["Generated test source did not parse as valid Java."])
        else:
            parsed_class = parsed.get("className")
            parsed_package = parsed.get("packageName") or ""
            if parsed_class != expected_class:
                errors.append(
                    f"Parsed class name '{parsed_class}' does not match declared testClassName '{expected_class}'."
                )
            if parsed_package != expected_package:
                errors.append(
                    f"Parsed package '{parsed_package}' does not match declared packageName '{expected_package}'."
                )
            if not target_path.endswith(f"{expected_class}.java"):
                errors.append(f"targetPath '{target_path}' does not end with '{expected_class}.java'.")

        return ValidationResult(
            valid=not errors,
            class_name=expected_class,
            package_name=expected_package,
            imports=list(parsed.get("imports") or []),
            errors=errors,
        )

    # -- OpenRewrite parse (via the CLI's `validate` mode) -------------------- #

    def _parse_source(self, source_code: str) -> dict:
        java = resolve_java_executable()
        jar = settings.rewrite_test_inventory_jar_path
        if not java or not jar.is_file():
            raise UnitTestToolUnavailableError(
                "The OpenRewrite test-inventory tool is not available to validate the generated test."
            )

        with tempfile.TemporaryDirectory(prefix="rewrite-validate-") as tmp:
            source_path = Path(tmp) / "GeneratedTest.java"
            output_path = Path(tmp) / "validate.json"
            source_path.write_text(source_code, encoding="utf-8")
            command = [java, "-jar", str(jar), "validate", str(source_path), str(output_path)]
            run_command(
                command,
                timeout=settings.unit_test_generated_class_timeout_seconds,
                env=build_tool_env(MIN_JAVA_MAJOR),
            )
            if not output_path.is_file():
                return {"valid": False, "parseErrors": ["OpenRewrite validation produced no output."]}
            return json.loads(output_path.read_text(encoding="utf-8"))
