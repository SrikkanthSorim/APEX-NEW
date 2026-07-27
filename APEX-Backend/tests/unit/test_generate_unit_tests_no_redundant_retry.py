"""Regression test: a transport-level failure GroqClient already retried
internally (timeout/429/5xx -- see RETRYABLE_STATUSES) must never also be
retried by the use case's own repair loop. Retrying it again there was the
actual cause of "the application retries the same request three times" /
"every failed class takes around 90 seconds" -- each of the ~3 repair-loop
iterations re-triggered GroqClient's own multi-second internal retry, so a
single class could take 3x as long as it should to fail."""

import tempfile
import unittest
from pathlib import Path

from app.application.use_cases.generate_unit_tests import GenerateUnitTestsUseCase
from app.core.config import settings
from app.domain.llm.llm_client import GENERATION_TEMPORARY_ERROR, LlmGenerationResult
from app.domain.models.unit_test_report import ClassInventoryEntry, MethodInventoryEntry, ProjectInventory


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


class _NeverInvokedTestRunner:
    def run_class(self, *args, **kwargs):
        raise AssertionError("Maven/Gradle must never run once Groq itself never returned a usable response")


class _AlwaysTemporaryErrorLlmClient:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, system_prompt: str, user_prompt: str) -> LlmGenerationResult:
        self.calls += 1
        return LlmGenerationResult(
            success=False, status=GENERATION_TEMPORARY_ERROR, http_status=503, retryable=True,
            message="Groq returned a temporary server error.",
        )


def _write_production_class(project_dir: Path, class_entry: ClassInventoryEntry) -> None:
    path = project_dir / class_entry.source_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"package com.example.service;\npublic class {class_entry.class_name} {{\n"
        "    public String describe(int type) { return \"x\"; }\n}\n",
        encoding="utf-8",
    )


class GenerateUnitTestsNoRedundantRetryTests(unittest.TestCase):
    def test_retryable_transport_failure_is_not_retried_again_by_the_repair_loop(self) -> None:
        original_repair_attempts = settings.unit_test_max_repair_attempts
        # A generous repair budget -- if the bug were still present, the
        # fake client would be called this many extra times too.
        settings.unit_test_max_repair_attempts = 5
        try:
            llm = _AlwaysTemporaryErrorLlmClient()
            use_case = GenerateUnitTestsUseCase(llm_client=llm, maven_runner=_NeverInvokedTestRunner())

            class_entry = _service_class("FlakyService")
            inventory = ProjectInventory(
                project_dir="/tmp", production_file_count=1, test_file_count=0,
                production_classes=[class_entry], test_classes=[],
            )

            with tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp)
                _write_production_class(project_dir, class_entry)

                result = use_case.execute(
                    "job_temp_error", project_dir, inventory,
                    java_version="17", spring_boot_version=None, build_tool="MAVEN",
                )
        finally:
            settings.unit_test_max_repair_attempts = original_repair_attempts

        # Exactly one call to the LLM client's generate() -- GroqClient's own
        # internal retry is what _AlwaysTemporaryErrorLlmClient stands in for
        # here (it's a test double for the whole generate() call, retries
        # included); the use case's repair loop must not call it again on
        # top of that despite a repair budget of 5.
        self.assertEqual(llm.calls, 1)
        self.assertEqual(result.failures[0]["type"], "GENERATION_FAILED")


if __name__ == "__main__":
    unittest.main()
