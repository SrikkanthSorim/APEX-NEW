"""Scenarios: Groq authentication failure (account-level, non-retryable) and an
invalid/unusable Groq JSON response."""

import tempfile
import unittest
from pathlib import Path

from app.domain.enums.unit_test_status import (
    GENERATION_STATUS_GENERATION_FAILED,
    GENERATION_STATUS_LLM_UNAVAILABLE,
)
from app.domain.llm.llm_client import (
    GENERATION_AUTHENTICATION_FAILED,
    GENERATION_INVALID_SCHEMA,
    LlmGenerationResult,
)
from app.domain.models.unit_test_report import ClassInventoryEntry, MethodInventoryEntry, ProjectInventory
from app.application.use_cases.generate_unit_tests import GenerateUnitTestsUseCase


def _service_class(name: str) -> ClassInventoryEntry:
    return ClassInventoryEntry(
        class_name=name,
        package_name="com.example.service",
        source_path=f"src/main/java/com/example/service/{name}.java",
        class_type="SERVICE",
        is_interface=False,
        is_abstract=False,
        annotations=[],
        dependencies=[],
        methods=[
            MethodInventoryEntry(
                name="describe", visibility="public", return_type="String",
                parameters=[], branch_count=1, throws_exceptions=False,
            )
        ],
        existing_test_class=None,
        existing_test_count=0,
    )


class _FakeMavenRunner:
    def run_class(self, *args, **kwargs):  # never reached in these scenarios
        raise AssertionError("Maven should never be invoked when the LLM call itself fails")


class _AuthFailingLlmClient:
    """Always fails with an account-level Groq authentication error (simulates
    a bad/missing GROQ_API_KEY, analogous to the old Hugging Face 402 case)."""

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, system_prompt: str, user_prompt: str) -> LlmGenerationResult:
        self.calls += 1
        return LlmGenerationResult(
            success=False,
            status=GENERATION_AUTHENTICATION_FAILED,
            http_status=401,
            retryable=False,
            message="Groq authentication failed. Check GROQ_API_KEY.",
        )


class _InvalidSchemaLlmClient:
    """Always returns a Groq-reported schema-validation failure (simulates a
    malformed/unusable model response that never reaches business validation)."""

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, system_prompt: str, user_prompt: str) -> LlmGenerationResult:
        self.calls += 1
        return LlmGenerationResult(
            success=False,
            status=GENERATION_INVALID_SCHEMA,
            http_status=None,
            retryable=False,
            message="Groq's response did not match the required test schema.",
        )


def _write_production_class(project_dir: Path, class_entry: ClassInventoryEntry) -> None:
    path = project_dir / class_entry.source_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"package com.example.service;\npublic class {class_entry.class_name} {{\n"
        "    public String describe(int type) { return \"x\"; }\n}\n",
        encoding="utf-8",
    )


class GroqAuthenticationFailureTests(unittest.TestCase):
    def test_authentication_failure_is_treated_as_non_retryable_and_stops_after_first_call(self) -> None:
        llm = _AuthFailingLlmClient()
        use_case = GenerateUnitTestsUseCase(llm_client=llm, maven_runner=_FakeMavenRunner())

        classes = [_service_class("TodoService"), _service_class("OrderService")]
        inventory = ProjectInventory(
            project_dir="/tmp", production_file_count=2, test_file_count=0,
            production_classes=classes, test_classes=[],
        )

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            for entry in classes:
                _write_production_class(project_dir, entry)

            result = use_case.execute(
                "job_401", project_dir, inventory,
                java_version="17", spring_boot_version=None, build_tool="MAVEN",
            )

        # Exactly one Groq call was made -- no retries, and the second class
        # was never attempted once the first one showed the account is
        # unavailable.
        self.assertEqual(llm.calls, 1)
        self.assertEqual(result.generation_status, GENERATION_STATUS_LLM_UNAVAILABLE)
        self.assertFalse(result.llm_available)
        self.assertEqual(result.generated_files, [])
        self.assertEqual(result.generated_test_case_count, 0)
        # No "missing required field" validation errors should ever be
        # recorded -- the failed call must never reach JSON-schema validation.
        self.assertEqual(result.failures, [])


class InvalidGroqSchemaTests(unittest.TestCase):
    def test_invalid_schema_is_retried_bounded_then_rejected_with_the_real_reason(self) -> None:
        llm = _InvalidSchemaLlmClient()
        use_case = GenerateUnitTestsUseCase(llm_client=llm, maven_runner=_FakeMavenRunner())

        class_entry = _service_class("TodoService")
        inventory = ProjectInventory(
            project_dir="/tmp", production_file_count=1, test_file_count=0,
            production_classes=[class_entry], test_classes=[],
        )

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            _write_production_class(project_dir, class_entry)

            result = use_case.execute(
                "job_bad_schema", project_dir, inventory,
                java_version="17", spring_boot_version=None, build_tool="MAVEN",
            )

        # Initial call + bounded retries, never unlimited.
        self.assertGreater(llm.calls, 1)
        self.assertLessEqual(llm.calls, 3)
        self.assertEqual(result.generation_status, GENERATION_STATUS_GENERATION_FAILED)
        self.assertTrue(result.llm_available)
        self.assertEqual(len(result.generated_files), 1)
        self.assertEqual(result.generated_files[0]["status"], "REJECTED")
        self.assertEqual(len(result.failures), 1)
        # The rejection reason must reflect the real Groq failure, never a
        # generic/misleading "missing required field" message.
        self.assertIn("did not match the required test schema", result.failures[0]["reason"])


if __name__ == "__main__":
    unittest.main()
