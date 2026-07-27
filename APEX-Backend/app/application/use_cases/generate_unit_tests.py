"""Generate Unit Tests use case (Steps 4-8 of the spec).

For each selected production class: build a bounded per-class LLM prompt,
call the LLM, validate the strict-JSON response (schema -> package/class
names -> target methods exist -> OpenRewrite parse -> duplicate check),
write the file only once validated, then compile + run it as the acceptance
gate. A compile failure triggers a controlled repair loop (real compiler
diagnostics sent back to the LLM), bounded by
``settings.unit_test_max_repair_attempts``. A test that compiles but fails at
runtime is still accepted -- Step 8: "When a test reveals a genuine
production-code problem, record it as a test failure or issue," not a
generation failure.

Never modifies production source code, never writes an unvalidated file, and
never leaves a broken (non-compiling) file behind -- a class that exhausts
its repair attempts is deleted and recorded as a failure instead.
"""

from __future__ import annotations

import logging
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.core.config import settings
from app.core.exceptions import LLMNotConfiguredError, LLMServiceError
from app.domain.enums.unit_test_status import (
    GENERATION_STATUS_GENERATED,
    GENERATION_STATUS_GENERATION_FAILED,
    GENERATION_STATUS_LLM_NOT_CONFIGURED,
    GENERATION_STATUS_LLM_UNAVAILABLE,
    GENERATION_STATUS_NO_CANDIDATES,
    GENERATION_STATUS_NOT_STARTED,
    GENERATION_STATUS_PARTIAL,
    GENERATION_STATUS_TIME_BUDGET_EXCEEDED,
    UnitTestStatus,
)
from app.domain.llm.llm_client import (
    GENERATION_AUTHENTICATION_FAILED,
    GENERATION_CONFIGURATION_ERROR,
    GENERATION_FORBIDDEN,
    GENERATION_RATE_LIMITED,
    GENERATION_TIMEOUT,
    RETRYABLE_STATUSES,
    LlmGenerationResult,
    UnitTestLlmClient,
)
from app.domain.models.unit_test_report import ClassInventoryEntry, ProjectInventory
from app.infrastructure.llm.groq_client import GroqClient, call_ceiling_seconds
from app.infrastructure.llm.prompt_templates import (
    UNIT_TEST_GENERATION_SYSTEM_PROMPT,
    UNIT_TEST_REPAIR_SYSTEM_PROMPT,
    build_unit_test_generation_prompt,
    build_unit_test_repair_prompt,
)
from app.infrastructure.testing.class_selector import select_classes_for_generation
from app.infrastructure.testing.gradle_test_runner import GradleTestRunner
from app.infrastructure.testing.maven_test_runner import MavenTestRunner
from app.infrastructure.testing.rewrite_test_validator import RewriteTestValidator
from app.infrastructure.testing.surefire_report_parser import parse_surefire_report_for_class

logger = logging.getLogger(__name__)

# Statuses where every remaining class would fail identically (bad/missing
# key, billing, permission) -- generation aborts the whole batch instead of
# burning the per-class repair budget on a dead end. Everything else (rate
# limit, timeout, invalid JSON/schema, request too large -- all already
# retried internally by GroqClient) is a per-class failure only.
_ABORT_BATCH_STATUSES = frozenset(
    {GENERATION_CONFIGURATION_ERROR, GENERATION_AUTHENTICATION_FAILED, GENERATION_FORBIDDEN}
)
_GENERATION_FAILURE_TYPES = frozenset({
    "GENERATION_FAILED",
    "GENERATION_TIMEOUT",
    "GENERATION_RATE_LIMITED",
    "VALIDATION_FAILED",
    "COMPILATION_FAILED",
    "GENERATION_ERROR",
    "WRITE_FAILED",
})

# Bounds the wall-clock a single class's Groq calls (initial attempt + every
# repair-loop attempt combined) are allowed to take -- see
# settings.unit_test_class_timeout_seconds. Each call runs on its own fresh
# daemon thread (see _call_llm_within_budget below), never a shared/bounded
# thread pool: a bounded pool meant an abandoned (still-running) call from
# one class could occupy a worker for the rest of the batch, so a *later*,
# unrelated class's call would sit queued behind it -- appearing to time out
# having never actually been attempted at all. A call that blows past its
# remaining per-class budget is abandoned (never awaited further) rather
# than waited on, so one slow class can never delay the next candidate class
# or the batch as a whole; daemon threads mean an abandoned call never keeps
# the process alive.


class _ClassBudget:
    """Per-class wall-clock deadline for Groq calls, shared across a class's
    initial-generation and repair-loop attempts so the *combined* time spent
    talking to Groq for one class never exceeds
    ``settings.unit_test_class_timeout_seconds`` -- not just any single call.
    """

    __slots__ = ("deadline", "timed_out")

    def __init__(self, deadline: float) -> None:
        self.deadline = deadline
        self.timed_out = False

    def remaining_seconds(self) -> float:
        return self.deadline - time.monotonic()

    def exhausted(self) -> bool:
        return self.timed_out or self.remaining_seconds() <= 0


def _failure_type(default: str, budget: "_ClassBudget") -> str:
    return "GENERATION_TIMEOUT" if budget.timed_out else default


def _java_string_literal(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _java_identifier_suffix(value: str) -> str:
    suffix = re.sub(r"[^0-9A-Za-z_]", "_", value or "method")
    if not suffix or suffix[0].isdigit():
        suffix = f"method_{suffix}"
    return suffix


@dataclass
class GenerationResult:
    generated_files: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    generated_test_case_count: int = 0
    llm_model: str | None = None
    llm_available: bool = True
    skip_reason: str | None = None
    generation_status: str = GENERATION_STATUS_NOT_STARTED
    timed_out_classes: int = 0
    skipped_classes: int = 0


def apply_generation_result(report: dict[str, Any], result: GenerationResult) -> dict[str, Any]:
    """Merge a ``GenerationResult`` onto a persisted unit-test-report dict.

    Shared by ``UnitTestPipeline.generate()`` and
    ``StartMigrationUseCase._run_unit_tests`` so the exact same fields
    (including the flattened ``generationStatus``/``existingTestFiles``/
    ``generatedTestFiles`` mirrors) are always produced the same way.
    Idempotent for progress saves: ``result`` is cumulative, so generation
    failures/files are replaced with the latest generation snapshot instead
    of appended on every class-completed callback. Execution-phase failures
    already persisted by ``RunUnitTestsUseCase`` are preserved.
    """
    summary = dict(report.get("summary") or {})
    accepted = [f for f in result.generated_files if f.get("status") != "REJECTED"]
    summary["newTestFiles"] = len(accepted)
    summary["generatedTestCases"] = result.generated_test_case_count
    summary["totalTestCases"] = int(summary.get("existingTestCases") or 0) + result.generated_test_case_count
    existing_execution_failures = [
        f for f in (report.get("failures") or []) if f.get("type") not in _GENERATION_FAILURE_TYPES
    ]
    report.update(
        summary=summary,
        generatedFiles=result.generated_files,
        failures=existing_execution_failures + _dedupe_failures(result.failures),
        llmModel=result.llm_model,
        llmProvider="groq",
        generationStatus=result.generation_status,
        existingTestFiles=summary.get("existingTestFiles", 0),
        existingTestCases=summary.get("existingTestCases", 0),
        generatedTestFiles=len(accepted),
    )
    if not result.llm_available:
        report["errorSummary"] = result.skip_reason
    if accepted:
        report["status"] = UnitTestStatus.TEST_GENERATED.value
    elif report.get("status") == UnitTestStatus.TEST_GENERATION_IN_PROGRESS.value:
        report["status"] = UnitTestStatus.TEST_ANALYSIS_COMPLETED.value
    return report


def _dedupe_failures(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for failure in failures:
        key = (
            str(failure.get("testClass") or ""),
            str(failure.get("testMethod") or ""),
            str(failure.get("type") or ""),
            str(failure.get("reason") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(failure)
    return deduped


class GenerateUnitTestsUseCase:
    def __init__(
        self,
        llm_client: UnitTestLlmClient | None = None,
        validator: RewriteTestValidator | None = None,
        maven_runner: MavenTestRunner | None = None,
        gradle_runner: GradleTestRunner | None = None,
    ) -> None:
        self._llm = llm_client or GroqClient()
        self._validator = validator or RewriteTestValidator()
        self._maven_runner = maven_runner or MavenTestRunner()
        self._gradle_runner = gradle_runner or GradleTestRunner()

    def _test_runner(self, build_tool: str) -> MavenTestRunner | GradleTestRunner:
        return self._gradle_runner if (build_tool or "").upper() == "GRADLE" else self._maven_runner

    def execute(
        self,
        job_id: str,
        project_dir: Path,
        inventory: ProjectInventory,
        *,
        java_version: str,
        spring_boot_version: str | None,
        build_tool: str,
        target_major: int | None = None,
        on_class_done: Callable[[GenerationResult, str, int, int], None] | None = None,
    ) -> GenerationResult:
        """``on_class_done(result_so_far, class_name, completed_count, total_count)``,
        if given, is invoked after each candidate class is attempted (whether it
        succeeded, was rejected, or errored) -- not on the batch-abort paths,
        since those return immediately after. Lets the caller persist progress
        incrementally instead of only after the whole (potentially very long)
        batch finishes.
        """
        candidates = select_classes_for_generation(inventory)
        if not candidates:
            return GenerationResult(generation_status=GENERATION_STATUS_NO_CANDIDATES)

        existing_test_class_names = {t.class_name for t in inventory.test_classes}
        result = GenerationResult()
        batch_start = time.monotonic()

        # Hard wall-clock ceiling on the *whole* batch (settings.
        # unit_test_generation_total_timeout_seconds) -- defense in depth on
        # top of the per-class timeout below, and also threaded into every
        # individual Groq call (see _call_llm_within_budget) so one call can
        # never by itself consume more than what's left of this budget. A
        # large repo with many candidate classes, or a Groq endpoint that is
        # merely slow rather than outright failing, must never be able to
        # hold up existing-test execution, JaCoCo, report persistence, or
        # migration completion.
        batch_deadline = batch_start + max(0.0, settings.unit_test_generation_total_timeout_seconds)
        total = len(candidates)

        def _report_progress(completed: int) -> None:
            if on_class_done is None:
                return
            try:
                on_class_done(result, class_entry.class_name, completed, total)
            except Exception:  # noqa: BLE001 - progress reporting must never break generation
                logger.exception("Unit test generation progress callback failed | job_id=%s", job_id)

        def _skip_remaining(from_index: int, reason: str, generation_status: str, skip_reason_message: str) -> None:
            remaining = candidates[from_index:]
            for skipped_entry in remaining:
                logger.warning(
                    "Unit test generation skipped | job_id=%s | class=%s | reason=%s",
                    job_id, skipped_entry.class_name, reason,
                )
            result.skipped_classes += len(remaining)
            result.generation_status = generation_status
            result.skip_reason = skip_reason_message

        for index, class_entry in enumerate(candidates):
            if time.monotonic() >= batch_deadline:
                _skip_remaining(
                    index, "TIME_BUDGET_EXCEEDED", GENERATION_STATUS_TIME_BUDGET_EXCEEDED,
                    f"Unit test generation stopped after {settings.unit_test_generation_total_timeout_seconds:.0f}s "
                    f"(time budget exceeded); {len(candidates) - index} candidate class(es) were not attempted.",
                )
                break
            try:
                outcome = self._generate_for_class(
                    job_id, project_dir, class_entry, existing_test_class_names,
                    java_version=java_version, spring_boot_version=spring_boot_version,
                    build_tool=build_tool, target_major=target_major,
                    batch_deadline=batch_deadline,
                )
            except LLMNotConfiguredError as exc:
                result.llm_available = False
                result.skip_reason = exc.message
                result.generation_status = GENERATION_STATUS_LLM_NOT_CONFIGURED
                logger.info(
                    "Groq unit test generation skipped | job_id=%s | class=%s | status=%s | retryable=false",
                    job_id, class_entry.class_name, GENERATION_STATUS_LLM_NOT_CONFIGURED,
                )
                break
            except LLMServiceError as exc:
                # Account-level failure (bad/missing key, billing, permission)
                # -- every remaining class would fail identically, so stop
                # spending the repair budget instead of retrying the same
                # dead end per class.
                result.llm_available = False
                result.skip_reason = exc.message
                result.generation_status = GENERATION_STATUS_LLM_UNAVAILABLE
                logger.warning(
                    "Groq unit test generation skipped | job_id=%s | class=%s | status=%s | http_status=%s | retryable=false",
                    job_id, class_entry.class_name, GENERATION_STATUS_LLM_UNAVAILABLE, exc.provider_status_code,
                )
                break
            except Exception:  # noqa: BLE001 - one class's failure must not stop the others
                logger.exception("Unexpected error generating tests for class %s", class_entry.class_name)
                result.failures.append({
                    "testClass": class_entry.class_name, "testMethod": "", "type": "GENERATION_ERROR",
                    "reason": "Unexpected error during test generation.",
                })
                _report_progress(index + 1)
                continue

            if outcome is None:
                _report_progress(index + 1)
            else:
                result.generated_files.append(outcome["file"])
                result.failures.extend(outcome["failures"])
                result.generated_test_case_count += outcome["testCount"]
                if outcome.get("llmModel"):
                    result.llm_model = outcome["llmModel"]
                if outcome.get("timedOut"):
                    result.timed_out_classes += 1
                if outcome["file"]["status"] != "REJECTED":
                    existing_test_class_names.add(outcome["file"]["className"])
                _report_progress(index + 1)

        if result.generation_status == GENERATION_STATUS_NOT_STARTED:
            accepted = [f for f in result.generated_files if f["status"] != "REJECTED"]
            rejected = [f for f in result.generated_files if f["status"] == "REJECTED"]
            if accepted and not rejected:
                result.generation_status = GENERATION_STATUS_GENERATED
            elif accepted and rejected:
                result.generation_status = GENERATION_STATUS_PARTIAL
            else:
                result.generation_status = GENERATION_STATUS_GENERATION_FAILED

        accepted_count = len([f for f in result.generated_files if f["status"] != "REJECTED"])
        if accepted_count:
            logger.info(
                "Generated tests validated | job_id=%s | generated_files=%d | generated_cases=%d",
                job_id, accepted_count, result.generated_test_case_count,
            )

        stage_duration_ms = int((time.monotonic() - batch_start) * 1000)
        logger.info(
            "Unit test generation stage stopped | job_id=%s | generated_files=%d | skipped_classes=%d | duration_ms=%d",
            job_id, accepted_count, result.skipped_classes, stage_duration_ms,
        )

        return result

    # -- per-class generation -------------------------------------------------- #

    def _generate_for_class(
        self,
        job_id: str,
        project_dir: Path,
        class_entry: ClassInventoryEntry,
        existing_test_class_names: set[str],
        *,
        java_version: str,
        spring_boot_version: str | None,
        build_tool: str,
        target_major: int | None,
        batch_deadline: float,
    ) -> dict[str, Any] | None:
        """Thin wrapper around ``_run_class_generation``: owns the per-class
        Groq wall-clock budget (settings.unit_test_class_timeout_seconds) and
        the started/completed/timed-out/failed log lines that bracket it, so
        every return path below (success, validation failure, compile
        failure, timeout, transport failure, exception) is covered by
        exactly one outcome log with an accurate duration_ms -- never a
        "started" with no matching outcome, and never a "completed" for a
        class whose generation actually failed (see ``_run_class_generation``,
        which logs the specific failure reason itself before returning).
        """
        production_source = self._read_source(project_dir, class_entry.source_path)
        if production_source is None:
            return None

        user_prompt = build_unit_test_generation_prompt(
            class_entry=class_entry,
            production_source=production_source,
            java_version=java_version,
            spring_boot_version=spring_boot_version,
            build_tool=build_tool,
            max_test_cases=settings.unit_test_max_cases_per_class,
        )

        class_timeout = settings.unit_test_class_timeout_seconds
        budget = _ClassBudget(deadline=time.monotonic() + class_timeout)
        class_start = time.monotonic()
        logger.info(
            "Groq unit test generation started | job_id=%s | class=%s | timeout_seconds=%.0f",
            job_id, class_entry.class_name, class_timeout,
        )
        outcome: dict[str, Any] | None = None
        try:
            outcome = self._run_class_generation(
                job_id, project_dir, class_entry, existing_test_class_names, user_prompt, budget,
                build_tool=build_tool, target_major=target_major,
                batch_deadline=batch_deadline,
            )
            return outcome
        finally:
            duration_ms = int((time.monotonic() - class_start) * 1000)
            if budget.timed_out:
                logger.warning(
                    "Groq unit test generation timed out | job_id=%s | class=%s | duration_ms=%d | status=GENERATION_TIMEOUT",
                    job_id, class_entry.class_name, duration_ms,
                )
            elif outcome is not None and outcome["file"]["status"] == "REJECTED":
                # A specific failure reason (transport failure/validation
                # failed/compile failed/write failed) was already logged by
                # _run_class_generation -- never also claim "completed" for
                # a class whose generation did not actually succeed.
                pass
            elif outcome is not None:
                logger.info(
                    "Groq unit test generation completed | job_id=%s | class=%s | duration_ms=%d",
                    job_id, class_entry.class_name, duration_ms,
                )
            if outcome is not None and budget.timed_out:
                outcome["timedOut"] = True

    def _run_class_generation(
        self,
        job_id: str,
        project_dir: Path,
        class_entry: ClassInventoryEntry,
        existing_test_class_names: set[str],
        user_prompt: str,
        budget: "_ClassBudget",
        *,
        build_tool: str,
        target_major: int | None,
        batch_deadline: float,
    ) -> dict[str, Any] | None:
        max_attempts = max(0, settings.unit_test_max_repair_attempts)
        attempt = 0
        fallback_mode = False

        llm_result = self._call_llm_within_budget(
            job_id, class_entry.class_name, UNIT_TEST_GENERATION_SYSTEM_PROMPT, user_prompt, budget, batch_deadline,
        )
        llm_model = llm_result.model or settings.groq_model

        # -- phase 0: a status in RETRYABLE_STATUSES (timeout/429/5xx) means
        #    GroqClient already retried this internally up to settings.
        #    unit_test_generation_max_retries times before ever returning
        #    success=False -- looping again here on top of that would blindly
        #    repeat the exact same failure and multiply wait time for no
        #    benefit ("retries the same request three times" / "every failed
        #    class takes around 90 seconds"), so those fail immediately.
        #    Anything else (malformed/invalid JSON or schema, a request Groq
        #    structurally rejected) is a real "got a response but it was
        #    unusable" case -- GroqClient never retried it, so it's still
        #    worth this bounded repair-loop retry, same as a validation/
        #    compile failure gets below. --
        while (
            not llm_result.success
            and llm_result.status not in RETRYABLE_STATUSES
            and attempt < max_attempts
            and not budget.exhausted()
        ):
            attempt += 1
            logger.warning(
                "Groq unit test generation failed | job_id=%s | class=%s | status=%s | retryable=%s",
                job_id, class_entry.class_name, llm_result.status, llm_result.retryable,
            )
            llm_result = self._call_llm_within_budget(
                job_id, class_entry.class_name, UNIT_TEST_GENERATION_SYSTEM_PROMPT, user_prompt, budget, batch_deadline,
            )
            if llm_result.model:
                llm_model = llm_result.model

        if not llm_result.success:
            # A failed/empty/timed-out Groq response is never validated as a
            # real generated test -- OpenRewrite validation is skipped and
            # this class is recorded as a failure so the migration continues.
            if llm_result.status in RETRYABLE_STATUSES:
                attempts = 1 + max(0, settings.unit_test_generation_max_retries) if llm_result.retryable else 1
            else:
                attempts = attempt + 1
            logger.warning(
                "Groq generation failed | job_id=%s | class=%s | status=%s | attempts=%d",
                job_id, class_entry.class_name, llm_result.status, attempts,
            )
            if llm_result.status == GENERATION_RATE_LIMITED:
                response = self._build_rate_limit_fallback_response(class_entry)
                if response is not None:
                    fallback_mode = True
                    llm_model = "deterministic-rate-limit-fallback"
                    logger.warning(
                        "Groq rate limited; using deterministic fallback generation | job_id=%s | class=%s | testCases=%d",
                        job_id, class_entry.class_name, len(response.get("testCases") or []),
                    )
                else:
                    return {
                        "file": {
                            "className": f"{class_entry.class_name}Test",
                            "path": "",
                            "testCount": 0,
                            "status": "REJECTED",
                        },
                        "failures": [{
                            "testClass": class_entry.class_name,
                            "testMethod": "",
                            "type": "GENERATION_RATE_LIMITED",
                            "reason": (llm_result.message or "Unit test generation was rate limited.")[:500],
                        }],
                        "testCount": 0,
                        "llmModel": llm_model,
                    }
            else:
                failure_type = _failure_type("GENERATION_FAILED", budget)
                return {
                    "file": {
                        "className": f"{class_entry.class_name}Test",
                        "path": "",
                        "testCount": 0,
                        "status": "REJECTED",
                    },
                    "failures": [{
                        "testClass": class_entry.class_name,
                        "testMethod": "",
                        "type": failure_type,
                        "reason": (llm_result.message or "Unit test generation failed.")[:500],
                    }],
                    "testCount": 0,
                    "llmModel": llm_model,
                }
        else:
            logger.info(
                "Groq response received | job_id=%s | class=%s | model=%s | testCases=%d",
                job_id, class_entry.class_name, llm_model, len(llm_result.data.test_cases),
            )
            response = llm_result.data.model_dump(by_alias=True)

        # -- phase 1: validate (schema/names/methods/OpenRewrite parse) -- #
        validation = self._validator.validate(
            response, class_entry=class_entry, existing_test_class_names=existing_test_class_names,
        )
        logger.info(
            "OpenRewrite validation result | job_id=%s | class=%s | valid=%s | errors=%d",
            job_id, class_entry.class_name, validation.valid, len(validation.errors),
        )
        while (
            not validation.valid
            and not fallback_mode
            and attempt < max_attempts
            and not budget.exhausted()
        ):
            attempt += 1
            diagnostics = "\n".join(validation.errors)
            repair_prompt = build_unit_test_repair_prompt(
                previous_source=str(response.get("sourceCode") or ""),
                compiler_diagnostics=diagnostics,
                class_entry=class_entry,
            )
            repair_result = self._call_llm_within_budget(
                job_id, class_entry.class_name, UNIT_TEST_REPAIR_SYSTEM_PROMPT, repair_prompt, budget, batch_deadline,
            )
            if repair_result.model:
                llm_model = repair_result.model
            if not repair_result.success:
                if repair_result.status == GENERATION_RATE_LIMITED:
                    fallback_response = self._build_rate_limit_fallback_response(class_entry)
                    if fallback_response is not None:
                        fallback_mode = True
                        llm_model = "deterministic-rate-limit-fallback"
                        response = fallback_response
                        validation = self._validator.validate(
                            response,
                            class_entry=class_entry,
                            existing_test_class_names=existing_test_class_names,
                        )
                        logger.warning(
                            "Groq rate limited during validation repair; using deterministic fallback generation | "
                            "job_id=%s | class=%s | testCases=%d",
                            job_id, class_entry.class_name, len(response.get("testCases") or []),
                        )
                        logger.info(
                            "OpenRewrite validation result | job_id=%s | class=%s | valid=%s | errors=%d",
                            job_id, class_entry.class_name, validation.valid, len(validation.errors),
                        )
                        break
                # The repair call itself failed at the API level -- stop
                # repairing this class with the last real validation errors
                # rather than looping on a dead API call.
                break
            response = repair_result.data.model_dump(by_alias=True)
            validation = self._validator.validate(
                response, class_entry=class_entry, existing_test_class_names=existing_test_class_names,
            )
            logger.info(
                "OpenRewrite validation result | job_id=%s | class=%s | valid=%s | errors=%d",
                job_id, class_entry.class_name, validation.valid, len(validation.errors),
            )

        if not validation.valid:
            logger.info(
                "Unit test generation rejected for %s after %d attempt(s): %s",
                class_entry.class_name, attempt + 1, "; ".join(validation.errors),
            )
            return {
                "file": {
                    "className": str(response.get("testClassName") or f"{class_entry.class_name}Test"),
                    "path": str(response.get("targetPath") or ""),
                    "testCount": 0,
                    "status": "REJECTED",
                },
                "failures": [{
                    "testClass": class_entry.class_name, "testMethod": "",
                    "type": _failure_type("VALIDATION_FAILED", budget),
                    "reason": "; ".join(validation.errors)[:500],
                }],
                "testCount": 0,
                "llmModel": llm_model,
            }

        target_path = str(response["targetPath"]).replace("\\", "/")
        source_code = str(response["sourceCode"])
        test_case_count = len(response.get("testCases") or [])
        logger.info(
            "Target test file path resolved | job_id=%s | class=%s | path=%s | testCases=%d",
            job_id, class_entry.class_name, target_path, test_case_count,
        )

        # -- phase 2: write + compile/run acceptance gate, with repair on
        #    compile failure only (a runtime test failure is still accepted).
        #    Unaffected by the class LLM timeout budget -- compiling/running
        #    already has its own independent, subprocess-level timeout (see
        #    settings.unit_test_generated_class_timeout_seconds); only the
        #    *repair* calls back to Groq below are budget-gated. -- #
        test_runner = self._test_runner(build_tool)
        while True:
            self._write_file(project_dir, target_path, source_code)
            written_path = (project_dir / target_path).resolve()
            if not written_path.is_file():
                # Should be unreachable (_write_file either writes the file or
                # raises) -- checked explicitly anyway so a REJECTED/PASSED
                # result is never reported for a file that doesn't physically
                # exist on disk.
                logger.warning(
                    "Generated test file missing after write | job_id=%s | class=%s | path=%s",
                    job_id, class_entry.class_name, target_path,
                )
                return {
                    "file": {
                        "className": validation.class_name, "path": target_path,
                        "testCount": 0, "status": "REJECTED",
                    },
                    "failures": [{
                        "testClass": class_entry.class_name, "testMethod": "", "type": "WRITE_FAILED",
                        "reason": "Generated test file was not found on disk after writing.",
                    }],
                    "testCount": 0,
                    "llmModel": llm_model,
                }
            logger.info(
                "Generated test file written | job_id=%s | class=%s | path=%s",
                job_id, class_entry.class_name, target_path,
            )
            fqcn = f"{validation.package_name}.{validation.class_name}" if validation.package_name else validation.class_name
            test_runner.run_class(project_dir, validation.class_name, target_major)
            execution = parse_surefire_report_for_class(project_dir, fqcn, build_tool)
            logger.info(
                "Compilation result | job_id=%s | class=%s | compiled=%s",
                job_id, class_entry.class_name, execution.available,
            )

            if execution.available:
                status = "PASSED" if execution.failed == 0 and execution.errors == 0 else "FAILED"
                failures = [f.to_dict() for f in execution.failures] if status == "FAILED" else []
                logger.info(
                    "Generated test validated | class=%s | path=%s | testCount=%s | status=%s",
                    validation.class_name, target_path, test_case_count, status,
                )
                return {
                    "file": {
                        "className": validation.class_name, "path": target_path,
                        "testCount": test_case_count, "status": status,
                    },
                    "failures": failures,
                    "testCount": test_case_count,
                    "llmModel": llm_model,
                }

            # Did not compile.
            if attempt >= max_attempts or budget.exhausted() or fallback_mode:
                self._delete_file(project_dir, target_path)
                logger.info(
                    "Generated test discarded after %d compile attempt(s): %s", attempt + 1, validation.class_name,
                )
                return {
                    "file": {
                        "className": validation.class_name, "path": target_path,
                        "testCount": 0, "status": "REJECTED",
                    },
                    "failures": [{
                        "testClass": validation.class_name, "testMethod": "",
                        "type": _failure_type("COMPILATION_FAILED", budget),
                        "reason": execution.reason or "Generated test failed to compile.",
                    }],
                    "testCount": 0,
                    "llmModel": llm_model,
                }

            attempt += 1
            diagnostics = execution.reason or "Compilation failed."
            repair_prompt = build_unit_test_repair_prompt(
                previous_source=source_code, compiler_diagnostics=diagnostics, class_entry=class_entry,
            )
            repair_result = self._call_llm_within_budget(
                job_id, class_entry.class_name, UNIT_TEST_REPAIR_SYSTEM_PROMPT, repair_prompt, budget, batch_deadline,
            )
            if repair_result.model:
                llm_model = repair_result.model
            if not repair_result.success:
                if repair_result.status == GENERATION_RATE_LIMITED:
                    fallback_response = self._build_rate_limit_fallback_response(class_entry)
                    if fallback_response is not None:
                        self._delete_file(project_dir, target_path)
                        fallback_validation = self._validator.validate(
                            fallback_response,
                            class_entry=class_entry,
                            existing_test_class_names=existing_test_class_names,
                        )
                        logger.warning(
                            "Groq rate limited during compile repair; using deterministic fallback generation | "
                            "job_id=%s | class=%s | testCases=%d",
                            job_id, class_entry.class_name, len(fallback_response.get("testCases") or []),
                        )
                        logger.info(
                            "OpenRewrite validation result | job_id=%s | class=%s | valid=%s | errors=%d",
                            job_id, class_entry.class_name, fallback_validation.valid, len(fallback_validation.errors),
                        )
                        if fallback_validation.valid:
                            response = fallback_response
                            validation = fallback_validation
                            target_path = str(response["targetPath"]).replace("\\", "/")
                            source_code = str(response["sourceCode"])
                            test_case_count = len(response.get("testCases") or [])
                            llm_model = "deterministic-rate-limit-fallback"
                            fallback_mode = True
                            continue
                self._delete_file(project_dir, target_path)
                return {
                    "file": {
                        "className": validation.class_name, "path": target_path, "testCount": 0, "status": "REJECTED",
                    },
                    "failures": [{
                        "testClass": class_entry.class_name, "testMethod": "",
                        "type": _failure_type("GENERATION_FAILED", budget),
                        "reason": (repair_result.message or "Unit test repair failed.")[:500],
                    }],
                    "testCount": 0,
                    "llmModel": llm_model,
                }
            response = repair_result.data.model_dump(by_alias=True)
            validation = self._validator.validate(
                response, class_entry=class_entry, existing_test_class_names=existing_test_class_names,
            )
            if not validation.valid:
                self._delete_file(project_dir, target_path)
                return {
                    "file": {
                        "className": str(response.get("testClassName") or validation.class_name or class_entry.class_name),
                        "path": target_path, "testCount": 0, "status": "REJECTED",
                    },
                    "failures": [{
                        "testClass": class_entry.class_name, "testMethod": "",
                        "type": _failure_type("VALIDATION_FAILED", budget),
                        "reason": "; ".join(validation.errors)[:500],
                    }],
                    "testCount": 0,
                    "llmModel": llm_model,
                }
            target_path = str(response["targetPath"]).replace("\\", "/")
            source_code = str(response["sourceCode"])
            test_case_count = len(response.get("testCases") or [])

    @staticmethod
    def _build_rate_limit_fallback_response(class_entry: ClassInventoryEntry) -> dict[str, Any] | None:
        method_names: list[str] = []
        seen: set[str] = set()
        for method in class_entry.methods:
            if not method.name or method.name in seen:
                continue
            seen.add(method.name)
            method_names.append(method.name)
            if len(method_names) >= max(1, settings.unit_test_max_cases_per_class):
                break
        if not method_names:
            return None

        test_class_name = f"{class_entry.class_name}Test"
        package_path = class_entry.package_name.replace(".", "/")
        target_path = f"src/test/java/{package_path}/{test_class_name}.java" if package_path else f"src/test/java/{test_class_name}.java"
        package_line = f"package {class_entry.package_name};\n\n" if class_entry.package_name else ""

        test_cases: list[dict[str, str]] = []
        test_methods: list[str] = []
        used_test_method_names: set[str] = set()
        for method_name in method_names:
            base_test_method_name = f"declares{_java_identifier_suffix(method_name).title().replace('_', '')}Method"
            test_method_name = base_test_method_name
            counter = 2
            while test_method_name in used_test_method_names:
                test_method_name = f"{base_test_method_name}{counter}"
                counter += 1
            used_test_method_names.add(test_method_name)
            method_literal = _java_string_literal(method_name)
            message_literal = _java_string_literal(f"Expected method '{method_name}' to exist")
            test_cases.append({
                "methodName": test_method_name,
                "targetMethod": method_name,
                "type": "POSITIVE",
                "scenario": f"Verify {class_entry.class_name} declares method {method_name}.",
                "expectedResult": f"The {method_name} method is present on {class_entry.class_name}.",
            })
            test_methods.append(
                "    @Test\n"
                f"    void {test_method_name}() {{\n"
                f"        assertTrue(declaredMethodNames().contains({method_literal}), {message_literal});\n"
                "    }\n"
            )

        test_methods_source = "\n".join(test_methods)
        source_code = package_line + (
            "import static org.junit.jupiter.api.Assertions.assertTrue;\n\n"
            "import java.lang.reflect.Method;\n"
            "import java.util.Arrays;\n"
            "import java.util.Set;\n"
            "import java.util.stream.Collectors;\n\n"
            "import org.junit.jupiter.api.Test;\n\n"
            f"class {test_class_name} {{\n"
            f"{test_methods_source}\n"
            "    private Set<String> declaredMethodNames() {\n"
            f"        return Arrays.stream({class_entry.class_name}.class.getDeclaredMethods())\n"
            "                .map(Method::getName)\n"
            "                .collect(Collectors.toSet());\n"
            "    }\n"
            "}\n"
        )
        return {
            "testClassName": test_class_name,
            "packageName": class_entry.package_name,
            "targetPath": target_path,
            "framework": "JUNIT_5",
            "testCases": test_cases,
            "sourceCode": source_code,
        }

    # -- LLM ---------------------------------------------------------------- #

    def _call_llm_within_budget(
        self,
        job_id: str,
        class_name: str,
        system_prompt: str,
        user_prompt: str,
        budget: "_ClassBudget",
        batch_deadline: float,
    ) -> LlmGenerationResult:
        """Run one Groq call (via ``_call_llm``), gated by this class's shared
        timeout budget and the whole batch's total timeout.

        Three distinct decisions are made here, deliberately not conflated:

        1. *Whether to start a new attempt at all* -- gated by the shrinking
           per-class budget (``budget.exhausted()``) and the total-batch
           deadline. Once either is exhausted, no further attempt (initial
           or repair) is started.
        2. *How long an attempt already in flight is allowed to run* -- never
           less than ``call_ceiling_seconds()``, i.e. never shorter than one
           legitimate ``GroqClient`` call's own connect+read+watchdog-slack
           ceiling. Using the (possibly much smaller) remaining per-class
           budget here instead would cut off a real, still-succeeding Groq
           response before GroqClient itself would ever have given up on it.
        3. ...but never more than what's left of the *total* generation
           timeout either (``settings.unit_test_generation_total_timeout_seconds``)
           -- a single call's own ceiling must never be allowed to blow the
           hard total-batch budget the caller configured.

        A call still running once its allotted time is exceeded is abandoned
        (never awaited further, matching ``GroqClient``'s own internal
        watchdog pattern) instead of blocking this class -- and therefore the
        whole batch -- indefinitely.
        """
        if budget.exhausted():
            budget.timed_out = True
            return LlmGenerationResult(
                success=False, status=GENERATION_TIMEOUT, http_status=None, retryable=False,
                message=(
                    f"Unit test generation for class '{class_name}' exceeded its configured "
                    f"timeout budget ({settings.unit_test_class_timeout_seconds:.0f}s) before this "
                    "attempt could start."
                ),
            )
        remaining_batch = batch_deadline - time.monotonic()
        if remaining_batch <= 0:
            budget.timed_out = True
            return LlmGenerationResult(
                success=False, status=GENERATION_TIMEOUT, http_status=None, retryable=False,
                message=(
                    f"Unit test generation for class '{class_name}' was not attempted: the total "
                    f"generation timeout ({settings.unit_test_generation_total_timeout_seconds:.0f}s) "
                    "was already exhausted."
                ),
            )
        call_timeout = min(max(budget.remaining_seconds(), call_ceiling_seconds()), remaining_batch)
        outcome_queue: "queue.SimpleQueue[Any]" = queue.SimpleQueue()

        def _run() -> None:
            try:
                outcome_queue.put(self._call_llm(job_id, class_name, system_prompt, user_prompt))
            except BaseException as exc:  # noqa: BLE001 - re-raised on the calling thread below
                outcome_queue.put(exc)

        threading.Thread(target=_run, daemon=True, name=f"unit-test-llm-call-{class_name}").start()
        try:
            outcome = outcome_queue.get(timeout=call_timeout)
        except queue.Empty:
            budget.timed_out = True
            return LlmGenerationResult(
                success=False, status=GENERATION_TIMEOUT, http_status=None, retryable=False,
                message=(
                    f"Unit test generation for class '{class_name}' exceeded its configured "
                    f"timeout budget ({settings.unit_test_class_timeout_seconds:.0f}s)."
                ),
            )
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def _call_llm(self, job_id: str, class_name: str, system_prompt: str, user_prompt: str) -> LlmGenerationResult:
        result = self._llm.generate(system_prompt, user_prompt)
        if not result.success and result.status in _ABORT_BATCH_STATUSES:
            if result.status == GENERATION_CONFIGURATION_ERROR:
                raise LLMNotConfiguredError(result.message)
            # AUTHENTICATION_FAILED / FORBIDDEN -- will fail identically on
            # every retry -- let it propagate so the caller aborts generation
            # for the whole job instead of burning the per-class repair budget.
            raise LLMServiceError(result.message, provider_status_code=result.http_status)
        return result

    # -- file I/O (job workspace only) --------------------------------------- #

    @staticmethod
    def _read_source(project_dir: Path, relative_path: str) -> str | None:
        path = project_dir / relative_path
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8", errors="ignore")

    @staticmethod
    def _write_file(project_dir: Path, relative_path: str, content: str) -> None:
        path = (project_dir / relative_path).resolve()
        if not str(path).startswith(str(project_dir.resolve())):
            raise ValueError("Generated test target path escapes the job workspace.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _delete_file(project_dir: Path, relative_path: str) -> None:
        path = project_dir / relative_path
        if path.is_file():
            path.unlink(missing_ok=True)
