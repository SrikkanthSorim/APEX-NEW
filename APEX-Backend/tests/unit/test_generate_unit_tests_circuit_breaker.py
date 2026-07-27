"""Scenario: Groq is rate-limited (HTTP 429) and stays rate-limited even
after GroqClient's own configured retry. Generation should not produce zero
new files or skip the rest of the batch; it should fall back to deterministic
JUnit contract tests generated from the OpenRewrite inventory."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.application.use_cases.generate_unit_tests import (
    GenerationResult,
    GenerateUnitTestsUseCase,
    apply_generation_result,
)
from app.domain.enums.unit_test_status import GENERATION_STATUS_GENERATED
from app.domain.llm.llm_client import (
    GENERATION_COMPLETED,
    GENERATION_RATE_LIMITED,
    GeneratedTestResponse,
    LlmGenerationResult,
)
from app.domain.models.unit_test_report import (
    ClassInventoryEntry,
    MethodInventoryEntry,
    ProjectInventory,
    TestExecutionSummary,
)
from app.infrastructure.testing.rewrite_test_validator import ValidationResult


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
        raise AssertionError("not used")


class _FakeTestRunner:
    def run_class(self, *args, **kwargs):
        return None


class _AcceptingValidator:
    def validate(self, response: dict, *, class_entry: ClassInventoryEntry, existing_test_class_names: set[str]):
        return ValidationResult(
            valid=True,
            class_name=str(response["testClassName"]),
            package_name=str(response["packageName"]),
        )


class _AlwaysRateLimitedLlmClient:
    """Simulates GroqClient having already exhausted its own internal retry
    for a 429 and given up -- exactly what generate_unit_tests.py sees once
    GroqClient's own retry budget (GROQ_MAX_RETRIES) is spent."""

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, system_prompt: str, user_prompt: str) -> LlmGenerationResult:
        self.calls += 1
        return LlmGenerationResult(
            success=False, status=GENERATION_RATE_LIMITED, http_status=429, retryable=True,
            message="The Groq rate limit was reached.",
        )


class _GeneratedThenRateLimitedRepairLlmClient:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, system_prompt: str, user_prompt: str) -> LlmGenerationResult:
        self.calls += 1
        if self.calls == 1:
            return LlmGenerationResult(
                success=True,
                status=GENERATION_COMPLETED,
                http_status=200,
                retryable=False,
                message="ok",
                model="test-model",
                data=GeneratedTestResponse(
                    testClassName="FirstServiceTest",
                    packageName="com.example.service",
                    targetPath="src/test/java/com/example/service/FirstServiceTest.java",
                    testCases=[{
                        "methodName": "generatedTest",
                        "targetMethod": "describe",
                        "type": "POSITIVE",
                        "scenario": "generated",
                        "expectedResult": "generated",
                    }],
                    sourceCode="package com.example.service; class FirstServiceTest {}",
                ),
            )
        return LlmGenerationResult(
            success=False,
            status=GENERATION_RATE_LIMITED,
            http_status=429,
            retryable=True,
            message="The Groq rate limit was reached.",
        )


def _write_production_class(project_dir: Path, class_entry: ClassInventoryEntry) -> None:
    path = project_dir / class_entry.source_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"package com.example.service;\npublic class {class_entry.class_name} {{\n"
        "    public String describe(int type) { return \"x\"; }\n}\n",
        encoding="utf-8",
    )


class GenerateUnitTestsCircuitBreakerTests(unittest.TestCase):
    def test_repeated_rate_limit_uses_fallback_and_continues_remaining_classes(self) -> None:
        llm = _AlwaysRateLimitedLlmClient()
        use_case = GenerateUnitTestsUseCase(
            llm_client=llm,
            validator=_AcceptingValidator(),
            maven_runner=_FakeTestRunner(),
        )

        classes = [_service_class("FirstService"), _service_class("SecondService")]
        inventory = ProjectInventory(
            project_dir="/tmp", production_file_count=2, test_file_count=0,
            production_classes=classes, test_classes=[],
        )

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            for entry in classes:
                _write_production_class(project_dir, entry)

            with patch(
                "app.application.use_cases.generate_unit_tests.parse_surefire_report_for_class",
                return_value=TestExecutionSummary(available=True, total=1, passed=1),
            ), self.assertLogs("app.application.use_cases.generate_unit_tests", level="WARNING") as captured:
                result = use_case.execute(
                    "job_rate_limited", project_dir, inventory,
                    java_version="17", spring_boot_version=None, build_tool="MAVEN",
                )

        self.assertEqual(llm.calls, 2)
        self.assertEqual(result.generation_status, GENERATION_STATUS_GENERATED)
        self.assertEqual(result.skipped_classes, 0)
        self.assertEqual(result.failures, [])
        self.assertEqual(len(result.generated_files), 2)
        self.assertEqual(result.generated_test_case_count, 2)
        self.assertTrue(all(file["status"] == "PASSED" for file in result.generated_files))

        self.assertTrue(
            any("using deterministic fallback generation" in line and "class=FirstService" in line
                for line in captured.output)
        )
        self.assertTrue(
            any("using deterministic fallback generation" in line and "class=SecondService" in line
                for line in captured.output)
        )
        self.assertFalse(any("GENERATION_SKIPPED_RATE_LIMITED" in line for line in captured.output))

    def test_compile_repair_rate_limit_uses_fallback_for_same_class(self) -> None:
        llm = _GeneratedThenRateLimitedRepairLlmClient()
        use_case = GenerateUnitTestsUseCase(
            llm_client=llm,
            validator=_AcceptingValidator(),
            maven_runner=_FakeTestRunner(),
        )

        classes = [_service_class("FirstService")]
        inventory = ProjectInventory(
            project_dir="/tmp", production_file_count=1, test_file_count=0,
            production_classes=classes, test_classes=[],
        )

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            _write_production_class(project_dir, classes[0])

            with patch(
                "app.application.use_cases.generate_unit_tests.parse_surefire_report_for_class",
                side_effect=[
                    TestExecutionSummary(available=False, reason="compile failed"),
                    TestExecutionSummary(available=True, total=1, passed=1),
                ],
            ), self.assertLogs("app.application.use_cases.generate_unit_tests", level="WARNING") as captured:
                result = use_case.execute(
                    "job_compile_repair_rate_limited",
                    project_dir,
                    inventory,
                    java_version="17",
                    spring_boot_version=None,
                    build_tool="MAVEN",
                )

        self.assertEqual(llm.calls, 2)
        self.assertEqual(result.generation_status, GENERATION_STATUS_GENERATED)
        self.assertEqual(result.failures, [])
        self.assertEqual(len(result.generated_files), 1)
        self.assertEqual(result.generated_files[0]["status"], "PASSED")
        self.assertEqual(result.llm_model, "deterministic-rate-limit-fallback")
        self.assertTrue(any("rate limited during compile repair" in line for line in captured.output))

    def test_apply_generation_result_is_idempotent_for_progress_snapshots(self) -> None:
        report = {"jobId": "job", "summary": {"existingTestCases": 1}, "failures": []}
        result = GenerationResult(
            generation_status=GENERATION_STATUS_GENERATED,
            failures=[{
                "testClass": "WeeklyAttendanceReportService",
                "testMethod": "",
                "type": "GENERATION_RATE_LIMITED",
                "reason": "The Groq rate limit was reached.",
            }],
        )

        report = apply_generation_result(report, result)
        report = apply_generation_result(report, result)

        self.assertEqual(len(report["failures"]), 1)


if __name__ == "__main__":
    unittest.main()
