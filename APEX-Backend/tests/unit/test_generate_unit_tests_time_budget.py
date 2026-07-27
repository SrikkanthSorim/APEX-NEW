"""Scenario: the overall Groq generation batch (settings.
unit_test_generation_total_timeout_seconds) runs out of time before every candidate
class can be attempted. This must stop the batch cleanly -- never hang, never
raise -- so existing-test execution (RunUnitTestsUseCase, called right after
generation in StartMigrationUseCase._run_unit_tests) always gets its turn."""

import tempfile
import unittest
from pathlib import Path

from app.application.use_cases.generate_unit_tests import GenerateUnitTestsUseCase
from app.core.config import settings
from app.domain.enums.unit_test_status import GENERATION_STATUS_TIME_BUDGET_EXCEEDED
from app.domain.llm.llm_client import GENERATION_COMPLETED, GeneratedTestResponse, LlmGenerationResult
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


class _FakeMavenRunner:
    def run_class(self, *args, **kwargs):
        raise AssertionError("Maven should never be invoked once the time budget is already exhausted")


class _NeverCalledLlmClient:
    """Would succeed instantly if called -- used to prove the batch stops
    *before* making any further Groq calls once the deadline has passed."""

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, system_prompt: str, user_prompt: str) -> LlmGenerationResult:
        self.calls += 1
        return LlmGenerationResult(
            success=True, status=GENERATION_COMPLETED, http_status=200, retryable=False,
            message="ok", model="test-model",
            data=GeneratedTestResponse(
                testClassName="XTest", packageName="com.example.service", targetPath="x",
                testCases=[{
                    "methodName": "t", "targetMethod": "describe", "type": "POSITIVE",
                    "scenario": "s", "expectedResult": "e",
                }],
                sourceCode="class XTest {}",
            ),
        )


def _write_production_class(project_dir: Path, class_entry: ClassInventoryEntry) -> None:
    path = project_dir / class_entry.source_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"package com.example.service;\npublic class {class_entry.class_name} {{\n"
        "    public String describe(int type) { return \"x\"; }\n}\n",
        encoding="utf-8",
    )


class GenerationTimeBudgetTests(unittest.TestCase):
    def test_zero_budget_stops_before_any_class_is_attempted(self) -> None:
        original_budget = settings.unit_test_generation_total_timeout_seconds
        settings.unit_test_generation_total_timeout_seconds = 0.0
        try:
            llm = _NeverCalledLlmClient()
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
                    "job_time_budget", project_dir, inventory,
                    java_version="17", spring_boot_version=None, build_tool="MAVEN",
                )
        finally:
            settings.unit_test_generation_total_timeout_seconds = original_budget

        self.assertEqual(llm.calls, 0)
        self.assertEqual(result.generation_status, GENERATION_STATUS_TIME_BUDGET_EXCEEDED)
        self.assertEqual(result.generated_files, [])
        self.assertIsNotNone(result.skip_reason)
        self.assertIn("time budget", (result.skip_reason or "").lower())


if __name__ == "__main__":
    unittest.main()
