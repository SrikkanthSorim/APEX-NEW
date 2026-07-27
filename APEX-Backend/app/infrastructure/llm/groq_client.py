"""Groq-backed implementation of ``UnitTestLlmClient`` (unit-test generation only).

Uses the official ``groq`` Python SDK's Chat Completions API. Every expected
failure mode (missing key, auth/billing, rate limit, timeout, temporary
server error, malformed/invalid JSON) is translated into a structured
``LlmGenerationResult`` instead of an exception -- see
``app/domain/llm/llm_client.py`` for why that contract matters. Only a truly
unexpected bug should ever raise out of :meth:`GroqClient.generate`.

Never logs the API key, request headers, full prompts, or full model
responses -- only status/outcome metadata.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import queue
import threading
import time
from typing import Any

import groq
import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.domain.llm.llm_client import (
    GENERATION_AUTHENTICATION_FAILED,
    GENERATION_COMPLETED,
    GENERATION_CONFIGURATION_ERROR,
    GENERATION_FAILED,
    GENERATION_FORBIDDEN,
    GENERATION_INVALID_JSON,
    GENERATION_INVALID_REQUEST,
    GENERATION_INVALID_SCHEMA,
    GENERATION_RATE_LIMITED,
    GENERATION_REQUEST_TOO_LARGE,
    GENERATION_TEMPORARY_ERROR,
    GENERATION_TIMEOUT,
    GeneratedTestResponse,
    LlmGenerationResult,
)

logger = logging.getLogger(__name__)

# HTTP statuses Groq/upstream can return that are worth retrying internally
# (transient -- not an auth/billing/request-shape problem). Matches the spec:
# retry Timeout/429/500/502/503/504; never 400/401/402/403/404 or an invalid
# API key/request shape (those fail identically on every attempt).
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_MAX_BACKOFF_SECONDS = 30.0
_JSON_SCHEMA_NAME = "unit_test_generation_result"

# Every call runs on its own fresh daemon thread (see _call_with_watchdog),
# never a shared/bounded thread pool. This is a watchdog of last resort:
# httpx's own `timeout=` (passed to `groq.Groq(...)` below) already bounds
# connect/read/write/pool separately, but DNS resolution for a blocked/
# unreachable host can stall the underlying socket call past that on some
# networks. Without this, that one stuck call would silently hang the
# calling thread forever -- exactly the "Groq unit test generation started"
# with no completion/failure/timeout log ever symptom this client must never
# produce. Daemon threads mean an abandoned (still-hung) call never keeps the
# process alive; a dedicated thread per call (rather than a small shared
# pool) means one -- or several -- abandoned calls can never starve a later,
# unrelated call of a worker to even start on (a real bug this project hit:
# a bounded pool of long-running abandoned calls left later classes queued
# behind them, timing out having never actually been attempted).
# Extra slack on top of the configured connect+read timeout so httpx's own
# timeout has a real chance to fire (and produce its own precise exception)
# before the watchdog's blunter TimeoutError does.
_WATCHDOG_SLACK_SECONDS = 5.0


def call_ceiling_seconds() -> float:
    """Worst-case wall-clock time a single ``GroqClient.generate()`` call can
    legitimately take before its own internal watchdog gives up: connect +
    read timeout, plus the watchdog's slack.

    Callers that layer an outer timeout on top of ``GroqClient`` (see
    ``GenerateUnitTestsUseCase._call_llm_within_budget``) must never use a
    shorter timeout than this for one *in-flight* call -- doing so would cut
    off a legitimate, still-succeeding response before GroqClient itself
    would ever have given up on it.
    """
    return settings.groq_connect_timeout_seconds + settings.groq_read_timeout_seconds + _WATCHDOG_SLACK_SECONDS


def _backoff_seconds(attempt: int) -> float:
    return min(float(2**attempt), _MAX_BACKOFF_SECONDS)


def _retry_after_seconds(exc: Exception, attempt: int) -> float:
    """How long to sleep before retrying a 429, honoring Groq's own
    ``Retry-After`` header but capped at ``_MAX_BACKOFF_SECONDS``.

    A rate-limit response can legitimately carry a ``Retry-After`` far larger
    than anything our own per-call/per-class budgets would ever wait out
    anyway (e.g. a daily-quota reset expressed in tens of minutes or hours).
    Sleeping the raw header value would tie up this call's worker thread for
    that entire duration even though the outer per-class watchdog is going
    to give up on it long before then -- capping keeps that abandonment
    prompt instead of leaving a thread needlessly blocked.
    """
    response = getattr(exc, "response", None)
    header = response.headers.get("retry-after") if response is not None else None
    if header:
        try:
            return min(max(0.0, float(header)), _MAX_BACKOFF_SECONDS)
        except ValueError:
            pass
    return _backoff_seconds(attempt)


def _strip_fences(content: str) -> str:
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]


def _is_response_format_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "response_format" in message or "json_schema" in message


class GroqClient:
    """Thin synchronous client over Groq's Chat Completions API.

    Matches the ``UnitTestLlmClient`` protocol -- swappable behind
    ``GenerateUnitTestsUseCase``'s ``llm_client`` constructor argument.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
        max_retries: int | None = None,
        max_completion_tokens: int | None = None,
    ) -> None:
        self._api_key = (api_key if api_key is not None else settings.groq_api_key).strip()
        self._model = (model or settings.groq_model).strip()
        self._connect_timeout = (
            connect_timeout if connect_timeout is not None else settings.groq_connect_timeout_seconds
        )
        self._read_timeout = read_timeout if read_timeout is not None else settings.groq_read_timeout_seconds
        # Wall-clock budget the watchdog (below) allows one call, before its
        # own slack -- connect + read covers the worst case of a slow-to-
        # connect host that then also streams a slow response.
        self._call_timeout = self._connect_timeout + self._read_timeout
        self._max_retries = max(
            0, max_retries if max_retries is not None else settings.unit_test_generation_max_retries
        )
        self._max_completion_tokens = max_completion_tokens or settings.groq_max_completion_tokens
        # `max_retries=0`: the SDK's own built-in retry/backoff is disabled so
        # every retry decision -- and every attempt -- goes through the
        # explicit, logged loop below. Left at the SDK default, a transient
        # error would be silently retried inside the library (no log line,
        # unpredictable extra delay stacked under our own retry loop) before
        # ever reaching this code, which is indistinguishable from a hang.
        # Separate connect/read timeouts (rather than one blanket value):
        # a host that's slow/unreachable to connect to should fail fast,
        # independent of how long a legitimately-streaming response is
        # allowed to take to finish reading.
        timeout_config = httpx.Timeout(
            connect=self._connect_timeout,
            read=self._read_timeout,
            write=self._read_timeout,
            pool=self._connect_timeout,
        )
        self._client = (
            groq.Groq(api_key=self._api_key, timeout=timeout_config, max_retries=0) if self._api_key else None
        )

    def generate(self, system_prompt: str, user_prompt: str) -> LlmGenerationResult:
        if not self._api_key or not self._client:
            return self._failure(
                GENERATION_CONFIGURATION_ERROR, None, False,
                "Groq API key is not configured (set GROQ_API_KEY).",
            )
        if not self._model:
            return self._failure(
                GENERATION_CONFIGURATION_ERROR, None, False,
                "Groq model is not configured (set GROQ_MODEL).",
            )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        attempt = 0
        use_json_schema = True
        allow_422_retry = True

        while True:
            try:
                completion = self._call_with_watchdog(messages, use_json_schema)
            except concurrent.futures.TimeoutError:
                if attempt >= self._max_retries:
                    return self._failure(
                        GENERATION_TIMEOUT, None, True,
                        "The Groq request did not respond within the configured timeout.",
                    )
                time.sleep(_backoff_seconds(attempt))
                attempt += 1
                continue
            except groq.RateLimitError as exc:
                if attempt >= self._max_retries:
                    return self._failure(GENERATION_RATE_LIMITED, 429, True, "The Groq rate limit was reached.")
                time.sleep(_retry_after_seconds(exc, attempt))
                attempt += 1
                continue
            except groq.AuthenticationError:
                return self._failure(
                    GENERATION_AUTHENTICATION_FAILED, 401, False,
                    "Groq authentication failed. Check GROQ_API_KEY.",
                )
            except groq.PermissionDeniedError:
                return self._failure(
                    GENERATION_FORBIDDEN, 403, False, "Groq denied access to the requested model.",
                )
            except groq.NotFoundError:
                return self._failure(
                    GENERATION_INVALID_REQUEST, 404, False,
                    f"The configured Groq model '{self._model}' was not found.",
                )
            except groq.UnprocessableEntityError:
                # Retry at most once with a corrected/simplified request --
                # never an unlimited loop.
                if allow_422_retry:
                    allow_422_retry = False
                    use_json_schema = False
                    messages[-1] = {
                        "role": "user",
                        "content": user_prompt + "\n\nReturn ONLY the JSON object described above. "
                        "No markdown fences, no commentary, no other text.",
                    }
                    continue
                return self._failure(GENERATION_INVALID_REQUEST, 422, False, "Groq could not process the request.")
            except groq.BadRequestError as exc:
                status_code = getattr(exc, "status_code", 400) or 400
                if status_code == 413:
                    return self._failure(
                        GENERATION_REQUEST_TOO_LARGE, 413, False, "The request was too large for Groq.",
                    )
                if use_json_schema and _is_response_format_error(exc):
                    # This model doesn't support JSON-Schema structured
                    # output -- fall back to JSON Object mode and retry the
                    # same call once (not a failure, just a capability probe).
                    use_json_schema = False
                    continue
                return self._failure(GENERATION_INVALID_REQUEST, status_code, False, "Groq rejected the request.")
            except groq.APITimeoutError:
                if attempt >= self._max_retries:
                    return self._failure(GENERATION_TIMEOUT, None, True, "The Groq request timed out.")
                time.sleep(_backoff_seconds(attempt))
                attempt += 1
                continue
            except groq.APIConnectionError:
                if attempt >= self._max_retries:
                    return self._failure(GENERATION_TEMPORARY_ERROR, None, True, "Groq could not be reached.")
                time.sleep(_backoff_seconds(attempt))
                attempt += 1
                continue
            except groq.InternalServerError as exc:
                status_code = getattr(exc, "status_code", 500) or 500
                if attempt >= self._max_retries:
                    return self._failure(
                        GENERATION_TEMPORARY_ERROR, status_code, True, "Groq returned a temporary server error.",
                    )
                time.sleep(_backoff_seconds(attempt))
                attempt += 1
                continue
            except groq.APIStatusError as exc:
                status_code = getattr(exc, "status_code", None)
                if status_code in _RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                    time.sleep(_backoff_seconds(attempt))
                    attempt += 1
                    continue
                return self._failure(GENERATION_FAILED, status_code, False, "Groq returned an unexpected error.")
            else:
                break

        model_used = getattr(completion, "model", None) or self._model
        content = self._extract_content(completion)
        try:
            parsed = json.loads(_strip_fences(content))
        except (TypeError, ValueError):
            return self._failure(GENERATION_INVALID_JSON, None, False, "Groq did not return valid JSON.", model_used)
        if not isinstance(parsed, dict):
            return self._failure(
                GENERATION_INVALID_JSON, None, False, "Groq's JSON response was not an object.", model_used,
            )

        try:
            data = GeneratedTestResponse.model_validate(parsed)
        except ValidationError:
            logger.info("Groq response failed schema validation | model=%s", model_used)
            return self._failure(
                GENERATION_INVALID_SCHEMA, None, False,
                "Groq's response did not match the required test schema.", model_used,
            )

        return LlmGenerationResult(
            success=True, status=GENERATION_COMPLETED, http_status=200, retryable=False,
            message="Groq generation completed.", model=model_used, data=data,
        )

    def verify_model_available(self) -> bool:
        """Optional startup check that ``GROQ_MODEL`` is actually listed by
        the Groq models API. Best-effort: never raises, never blocks boot --
        a transient failure here just means the check couldn't be completed,
        not that the model is unavailable.
        """
        if not self._client:
            return False
        try:
            models = self._client.models.list()
        except Exception:
            logger.warning("Could not verify Groq model availability | model=%s", self._model)
            return True
        available_ids = {m.id for m in getattr(models, "data", []) or []}
        if self._model not in available_ids:
            logger.warning("Configured Groq model may not be available | model=%s", self._model)
            return False
        return True

    # -- helpers -------------------------------------------------------------- #

    def _call_with_watchdog(self, messages: list[dict[str, str]], use_json_schema: bool) -> Any:
        """Run the blocking Groq HTTP call under a hard wall-clock deadline,
        on its own dedicated daemon thread (never a shared pool -- see the
        module-level comment above _WATCHDOG_SLACK_SECONDS).

        Raises whatever the SDK call itself raised (RateLimitError,
        AuthenticationError, APITimeoutError, ...) unchanged so every existing
        ``except groq.*`` branch above keeps working -- this only adds an
        outer ``concurrent.futures.TimeoutError`` for the case where the call
        never returns *at all* within ``self._timeout`` (+ slack), which
        httpx's own timeout does not always cover (e.g. a stalled DNS lookup).
        """
        outcome_queue: "queue.SimpleQueue[Any]" = queue.SimpleQueue()

        def _run() -> None:
            try:
                completion = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=0.2,
                    max_completion_tokens=self._max_completion_tokens,
                    response_format=self._response_format(use_json_schema),
                )
            except BaseException as exc:  # noqa: BLE001 - re-raised on the calling thread below
                outcome_queue.put(exc)
            else:
                outcome_queue.put(completion)

        threading.Thread(target=_run, daemon=True, name="groq-call-watchdog").start()
        try:
            outcome = outcome_queue.get(timeout=self._call_timeout + _WATCHDOG_SLACK_SECONDS)
        except queue.Empty:
            raise concurrent.futures.TimeoutError() from None
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    @staticmethod
    def _extract_content(completion: Any) -> str:
        try:
            return completion.choices[0].message.content or ""
        except (AttributeError, IndexError):
            return ""

    @staticmethod
    def _response_format(use_json_schema: bool) -> dict[str, Any]:
        if not use_json_schema:
            return {"type": "json_object"}
        schema = GeneratedTestResponse.model_json_schema(by_alias=True)
        schema["additionalProperties"] = False
        return {
            "type": "json_schema",
            "json_schema": {"name": _JSON_SCHEMA_NAME, "schema": schema, "strict": False},
        }

    def _failure(
        self,
        status: str,
        http_status: int | None,
        retryable: bool,
        message: str,
        model: str | None = None,
    ) -> LlmGenerationResult:
        logger.warning(
            "Groq API call failed | status=%s | http_status=%s | retryable=%s", status, http_status, retryable,
        )
        return LlmGenerationResult(
            success=False, status=status, http_status=http_status, retryable=retryable,
            message=message, model=model or self._model,
        )
