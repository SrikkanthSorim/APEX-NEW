"""Provider-agnostic contract for unit-test-generation LLM calls.

Any provider (Groq today -- see ``app/infrastructure/llm/groq_client.py`` --
another provider tomorrow) implements ``UnitTestLlmClient.generate`` and
returns an ``LlmGenerationResult``. Unlike ``HuggingFaceClient.chat_json``
(used by the separate Java Version Recommendation feature), this contract
never raises for an ordinary provider failure -- a bad API key, a rate limit,
a timeout, or a malformed model response are all just data on the returned
result. That is what lets ``GenerateUnitTestsUseCase`` tell "the API call
itself failed" apart from "the API call succeeded with a response that fails
validation" and avoid ever reporting a misleading "missing required field"
error when the real problem was an API failure.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

# -- structured result status vocabulary ------------------------------------
#
# These mirror Groq's own outcome vocabulary today (the only implementation).
# A future second provider is expected to map its own errors onto this same
# set rather than inventing a parallel one, so callers stay provider-agnostic.

GENERATION_COMPLETED = "GROQ_COMPLETED"
GENERATION_CONFIGURATION_ERROR = "GROQ_CONFIGURATION_ERROR"
GENERATION_AUTHENTICATION_FAILED = "GROQ_AUTHENTICATION_FAILED"
GENERATION_FORBIDDEN = "GROQ_FORBIDDEN"
GENERATION_RATE_LIMITED = "GROQ_RATE_LIMITED"
GENERATION_REQUEST_TOO_LARGE = "GROQ_REQUEST_TOO_LARGE"
GENERATION_INVALID_REQUEST = "GROQ_INVALID_REQUEST"
GENERATION_TIMEOUT = "GROQ_TIMEOUT"
GENERATION_TEMPORARY_ERROR = "GROQ_TEMPORARY_ERROR"
GENERATION_INVALID_JSON = "GROQ_INVALID_JSON"
GENERATION_INVALID_SCHEMA = "GROQ_INVALID_SCHEMA"
GENERATION_FAILED = "GROQ_FAILED"

# Statuses where every remaining class in the batch would fail identically --
# callers should stop spending their per-class repair budget and abort the
# whole generation run instead of retrying the same dead end per class.
ACCOUNT_LEVEL_STATUSES = frozenset(
    {GENERATION_CONFIGURATION_ERROR, GENERATION_AUTHENTICATION_FAILED, GENERATION_FORBIDDEN}
)

# Statuses worth a bounded caller-level retry of the same request (the
# provider's own internal retry budget -- see GroqClient -- is already
# exhausted by the time a caller ever sees one of these).
RETRYABLE_STATUSES = frozenset(
    {GENERATION_RATE_LIMITED, GENERATION_TIMEOUT, GENERATION_TEMPORARY_ERROR}
)


class GeneratedTestCase(BaseModel):
    """One entry of the strict-JSON ``testCases`` array (see the spec)."""

    model_config = ConfigDict(populate_by_name=True)

    method_name: str = Field(alias="methodName", min_length=1)
    target_method: str = Field(alias="targetMethod", min_length=1)
    type: Literal["POSITIVE", "NEGATIVE", "BOUNDARY", "EXCEPTION"]
    scenario: str = Field(min_length=1)
    expected_result: str = Field(alias="expectedResult", min_length=1)


class GeneratedTestResponse(BaseModel):
    """The strict JSON object the unit-test generation prompt requires.

    Validated before anything from it is ever written to disk or handed to
    the OpenRewrite/compile pipeline -- see ``RewriteTestValidator`` for the
    deeper business-rule checks (duplicate names, target methods actually
    existing, real Java parse) that run once this structural check passes.
    """

    model_config = ConfigDict(populate_by_name=True)

    test_class_name: str = Field(alias="testClassName", min_length=1)
    package_name: str = Field(alias="packageName", default="")
    target_path: str = Field(alias="targetPath", min_length=1)
    framework: Literal["JUNIT_5"] = "JUNIT_5"
    test_cases: list[GeneratedTestCase] = Field(alias="testCases", min_length=1)
    source_code: str = Field(alias="sourceCode", min_length=1)


class LlmGenerationResult(BaseModel):
    """Structured outcome of a single ``UnitTestLlmClient.generate`` call.

    ``success=False`` is a normal, expected outcome (bad key, rate limit,
    timeout, malformed response) -- never an exception. Callers must check
    ``success`` before touching ``data`` and must never run JSON-schema
    validation against a failed call.
    """

    model_config = ConfigDict(populate_by_name=True)

    success: bool
    status: str
    http_status: int | None = Field(default=None, alias="httpStatus")
    retryable: bool = False
    message: str
    model: str | None = None
    data: GeneratedTestResponse | None = None

    @property
    def is_account_level_failure(self) -> bool:
        return self.status in ACCOUNT_LEVEL_STATUSES


class UnitTestLlmClient(Protocol):
    """Contract ``GenerateUnitTestsUseCase`` depends on -- swap providers by
    passing a different implementation, no use-case changes required."""

    def generate(self, system_prompt: str, user_prompt: str) -> LlmGenerationResult: ...
