"""Scenarios covering the per-class Groq timeout budget
(settings.unit_test_class_timeout_seconds), and specifically the bug it used
to have: an in-flight call was cut off using the (small) *remaining* class
budget directly, which is often shorter than a single legitimate Groq call
is allowed to take (GroqClient's own connect+read+watchdog-slack ceiling --
see groq_client.call_ceiling_seconds()). That meant a real, still-succeeding
Groq response could be -- and in practice regularly was -- abandoned and
reported as GENERATION_TIMEOUT before it ever had a fair chance to finish,
which is why generation could produce zero new test files even though Groq
was configured correctly and responding.

The fix: a call already in flight is never cut off before
``call_ceiling_seconds()`` has elapsed, no matter how little of the nominal
per-class budget remains. Only the decision to *start a new* attempt
(initial or repair) is gated by the shrinking budget. A call that genuinely
outlives even that ceiling is still abandoned -- generation can never hang
indefinitely on one class."""

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.application.use_cases.generate_unit_tests import GenerateUnitTestsUseCase
from app.core.config import settings
from app.domain.llm.llm_client import GENERATION_FAILED, GENERATION_INVALID_REQUEST, LlmGenerationResult
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
        raise AssertionError("Maven/Gradle must never run for a class whose Groq call already failed")


class _SleepThenFailLlmClient:
    """Every call sleeps for a fixed duration, then returns a deliberate
    (non-timeout) failure -- isolates the timeout/abandonment mechanism
    itself without needing a real OpenRewrite validator/compile pipeline."""

    def __init__(self, sleep_seconds: float) -> None:
        self.sleep_seconds = sleep_seconds
        self.call_count = 0

    def generate(self, system_prompt: str, user_prompt: str) -> LlmGenerationResult:
        self.call_count += 1
        time.sleep(self.sleep_seconds)
        return LlmGenerationResult(
            success=False, status=GENERATION_FAILED, http_status=500, retryable=True,
            message="deliberate, real failure -- proves the call was allowed to actually finish",
        )


class _OneSlowThenFastLlmClient:
    """First call (the first candidate class) sleeps far longer than even
    the (patched, tiny) Groq call ceiling; the second call (the next
    candidate class) fails fast."""

    def __init__(self, slow_seconds: float) -> None:
        self.slow_seconds = slow_seconds
        self.call_count = 0

    def generate(self, system_prompt: str, user_prompt: str) -> LlmGenerationResult:
        self.call_count += 1
        if self.call_count == 1:
            time.sleep(self.slow_seconds)
            return LlmGenerationResult(
                success=False, status=GENERATION_FAILED, http_status=500, retryable=True,
                message="should never be observed -- the caller must give up before this returns",
            )
        return LlmGenerationResult(
            success=False, status=GENERATION_INVALID_REQUEST, http_status=400, retryable=False,
            message="fast, deliberate failure for the second class",
        )


def _write_production_class(project_dir: Path, class_entry: ClassInventoryEntry) -> None:
    path = project_dir / class_entry.source_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"package com.example.service;\npublic class {class_entry.class_name} {{\n"
        "    public String describe(int type) { return \"x\"; }\n}\n",
        encoding="utf-8",
    )


class GenerateUnitTestsClassTimeoutTests(unittest.TestCase):
    def test_call_exceeding_nominal_budget_but_within_groq_ceiling_is_not_cut_off(self) -> None:
        # Regression test for the actual production bug: a nominal per-class
        # budget (0.2s here) smaller than a real Groq call's own allowed
        # ceiling (patched to 1.0s, standing in for connect+read+slack) must
        # NOT abandon a call that finishes within that ceiling -- it must be
        # allowed to complete and its real outcome (a failure, in this case)
        # must be reported honestly, never mislabeled GENERATION_TIMEOUT.
        original_class_timeout = settings.unit_test_class_timeout_seconds
        original_repair_attempts = settings.unit_test_max_repair_attempts
        settings.unit_test_class_timeout_seconds = 0.2
        settings.unit_test_max_repair_attempts = 0
        try:
            llm = _SleepThenFailLlmClient(sleep_seconds=0.5)
            use_case = GenerateUnitTestsUseCase(llm_client=llm, maven_runner=_NeverInvokedTestRunner())
            classes = [_service_class("SlowButRealService")]
            inventory = ProjectInventory(
                project_dir="/tmp", production_file_count=1, test_file_count=0,
                production_classes=classes, test_classes=[],
            )

            with tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp)
                _write_production_class(project_dir, classes[0])

                with patch(
                    "app.application.use_cases.generate_unit_tests.call_ceiling_seconds", return_value=1.0,
                ):
                    result = use_case.execute(
                        "job_within_ceiling", project_dir, inventory,
                        java_version="17", spring_boot_version=None, build_tool="MAVEN",
                    )
        finally:
            settings.unit_test_class_timeout_seconds = original_class_timeout
            settings.unit_test_max_repair_attempts = original_repair_attempts

        self.assertEqual(llm.call_count, 1)
        self.assertEqual(result.timed_out_classes, 0)
        failure = result.failures[0]
        self.assertEqual(failure["type"], "GENERATION_FAILED")
        self.assertNotEqual(failure["type"], "GENERATION_TIMEOUT")

    def test_call_exceeding_groq_ceiling_is_abandoned_and_next_class_still_runs(self) -> None:
        original_class_timeout = settings.unit_test_class_timeout_seconds
        original_repair_attempts = settings.unit_test_max_repair_attempts
        original_total_timeout = settings.unit_test_generation_total_timeout_seconds
        settings.unit_test_class_timeout_seconds = 0.2
        settings.unit_test_max_repair_attempts = 0
        settings.unit_test_generation_total_timeout_seconds = 30.0
        try:
            llm = _OneSlowThenFastLlmClient(slow_seconds=5.0)
            use_case = GenerateUnitTestsUseCase(llm_client=llm, maven_runner=_NeverInvokedTestRunner())

            classes = [_service_class("SlowService"), _service_class("FastService")]
            inventory = ProjectInventory(
                project_dir="/tmp", production_file_count=2, test_file_count=0,
                production_classes=classes, test_classes=[],
            )

            with tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp)
                for entry in classes:
                    _write_production_class(project_dir, entry)

                started = time.monotonic()
                with patch(
                    "app.application.use_cases.generate_unit_tests.call_ceiling_seconds", return_value=0.3,
                ):
                    result = use_case.execute(
                        "job_class_timeout", project_dir, inventory,
                        java_version="17", spring_boot_version=None, build_tool="MAVEN",
                    )
                elapsed = time.monotonic() - started
        finally:
            settings.unit_test_class_timeout_seconds = original_class_timeout
            settings.unit_test_max_repair_attempts = original_repair_attempts
            settings.unit_test_generation_total_timeout_seconds = original_total_timeout

        # Bounded by the (patched, tiny) Groq call ceiling, nowhere near the
        # 5s the first class's call actually sleeps for -- proves the slow
        # class was abandoned, not awaited, and the next class still ran.
        self.assertLess(elapsed, 3.0)
        self.assertEqual(llm.call_count, 2)
        self.assertEqual(result.timed_out_classes, 1)
        self.assertEqual(len(result.failures), 2)

        slow_failure = next(f for f in result.failures if f["testClass"] == "SlowService")
        fast_failure = next(f for f in result.failures if f["testClass"] == "FastService")
        self.assertEqual(slow_failure["type"], "GENERATION_TIMEOUT")
        self.assertNotEqual(fast_failure["type"], "GENERATION_TIMEOUT")


if __name__ == "__main__":
    unittest.main()
