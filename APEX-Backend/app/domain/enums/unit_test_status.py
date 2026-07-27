"""Status values for the automatic unit-test analysis/generation/execution
pipeline (see UnitTestReport). Distinct from MigrationStatus -- a unit-test
failure never changes the migration's own status.
"""

from __future__ import annotations

from enum import Enum


class UnitTestStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    TEST_ANALYSIS_COMPLETED = "TEST_ANALYSIS_COMPLETED"
    NO_TESTS_FOUND = "NO_TESTS_FOUND"
    TEST_GENERATION_IN_PROGRESS = "TEST_GENERATION_IN_PROGRESS"
    TEST_GENERATED = "TEST_GENERATED"
    TEST_COMPILATION_FAILED = "TEST_COMPILATION_FAILED"
    TEST_EXECUTION_PASSED = "TEST_EXECUTION_PASSED"
    TEST_EXECUTION_FAILED = "TEST_EXECUTION_FAILED"
    TEST_EXECUTION_TIMEOUT = "TEST_EXECUTION_TIMEOUT"
    TEST_NOT_EXECUTED = "TEST_NOT_EXECUTED"
    REPORT_GENERATED = "REPORT_GENERATED"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ISSUES = "COMPLETED_WITH_ISSUES"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in (
            UnitTestStatus.NO_TESTS_FOUND,
            UnitTestStatus.TEST_COMPILATION_FAILED,
            UnitTestStatus.COMPLETED,
            UnitTestStatus.COMPLETED_WITH_ISSUES,
            UnitTestStatus.FAILED,
        )


# -- generation status (per job, describes the LLM generation phase only) -- #

GENERATION_STATUS_NOT_STARTED = "NOT_STARTED"
GENERATION_STATUS_NO_CANDIDATES = "NO_CANDIDATES"
GENERATION_STATUS_GENERATED = "GENERATED"
GENERATION_STATUS_PARTIAL = "PARTIAL"
GENERATION_STATUS_GENERATION_FAILED = "GENERATION_FAILED"
GENERATION_STATUS_LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
GENERATION_STATUS_LLM_NOT_CONFIGURED = "LLM_NOT_CONFIGURED"
# The batch's overall wall-clock budget
# (settings.unit_test_generation_total_timeout_seconds) ran out before every
# candidate class could be processed -- distinct from GENERATION_FAILED (a
# real per-call failure) so it's obvious from the report alone that this was
# a time-budget cutoff, not a Groq/validation error.
GENERATION_STATUS_TIME_BUDGET_EXCEEDED = "TIME_BUDGET_EXCEEDED"
# The master switch (settings.unit_test_execution_enabled) is off.
GENERATION_STATUS_DISABLED = "DISABLED"
# Legacy generation status kept so older persisted reports still render. New
# generation runs use deterministic fallback tests when Groq is rate-limited
# instead of skipping the rest of the candidate batch.
GENERATION_STATUS_SKIPPED_RATE_LIMITED = "SKIPPED_RATE_LIMITED"

# -- test execution status (per run, describes compile+execute only) -------- #

TEST_EXECUTION_STATUS_NO_TESTS_EXECUTED = "NO_TESTS_EXECUTED"
TEST_EXECUTION_STATUS_COMPILATION_FAILED = "TEST_COMPILATION_FAILED"
TEST_EXECUTION_STATUS_FAILED = "TEST_EXECUTION_FAILED"
TEST_EXECUTION_STATUS_PASSED = "TEST_EXECUTION_PASSED"
TEST_EXECUTION_STATUS_TIMEOUT = "TEST_EXECUTION_TIMEOUT"

# -- coverage status (per run, describes whether JaCoCo XML was usable) ----- #

COVERAGE_STATUS_GENERATED = "COVERAGE_REPORT_GENERATED"
COVERAGE_STATUS_MISSING = "COVERAGE_REPORT_MISSING"
COVERAGE_STATUS_INVALID = "COVERAGE_REPORT_INVALID"
