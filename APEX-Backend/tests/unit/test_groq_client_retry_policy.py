"""Scenario: GroqClient must retry only temporary/transient failures (timeout,
429, 500, 502, 503, 504) and never retry account-level/request-shape failures
(400, 401, 402, 403, 404, invalid API key, invalid request). See
GroqClient._RETRYABLE_STATUS_CODES / groq_client.py's per-exception handling.
"""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

import groq

from app.domain.llm.llm_client import GENERATION_COMPLETED, GENERATION_INVALID_REQUEST
from app.infrastructure.llm.groq_client import GroqClient


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code=status_code, request=httpx.Request("POST", "https://api.groq.test/x"))


def _fake_completion() -> SimpleNamespace:
    payload = {
        "testClassName": "FooTest",
        "packageName": "com.example",
        "targetPath": "src/test/java/com/example/FooTest.java",
        "framework": "JUNIT_5",
        "testCases": [{
            "methodName": "t", "targetMethod": "doWork", "type": "POSITIVE",
            "scenario": "s", "expectedResult": "e",
        }],
        "sourceCode": "class FooTest {}",
    }
    message = SimpleNamespace(content=json.dumps(payload))
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(model="llama-3.3-70b-versatile", choices=[choice])


class GroqClientRetryPolicyTests(unittest.TestCase):
    def _client(self, max_retries: int = 1) -> GroqClient:
        return GroqClient(
            api_key="test-key", model="test-model",
            connect_timeout=1.0, read_timeout=1.0, max_retries=max_retries,
        )

    def test_rate_limit_retried_once_then_succeeds(self) -> None:
        client = self._client(max_retries=1)
        calls = {"count": 0}

        def _create(**kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise groq.RateLimitError("rate limited", response=_response(429), body=None)
            return _fake_completion()

        client._client.chat.completions.create = _create  # type: ignore[attr-defined]

        with patch("time.sleep", return_value=None):
            result = client.generate("system", "user")

        self.assertEqual(calls["count"], 2)
        self.assertTrue(result.success)
        self.assertEqual(result.status, GENERATION_COMPLETED)

    def test_payment_required_is_never_retried(self) -> None:
        client = self._client(max_retries=1)
        calls = {"count": 0}

        def _create(**kwargs):
            calls["count"] += 1
            raise groq.APIStatusError("payment required", response=_response(402), body=None)

        client._client.chat.completions.create = _create  # type: ignore[attr-defined]

        with patch("time.sleep", return_value=None):
            result = client.generate("system", "user")

        self.assertEqual(calls["count"], 1)
        self.assertFalse(result.success)
        self.assertFalse(result.retryable)

    def test_not_found_model_is_never_retried(self) -> None:
        client = self._client(max_retries=2)
        calls = {"count": 0}

        def _create(**kwargs):
            calls["count"] += 1
            raise groq.NotFoundError("model not found", response=_response(404), body=None)

        client._client.chat.completions.create = _create  # type: ignore[attr-defined]

        with patch("time.sleep", return_value=None):
            result = client.generate("system", "user")

        self.assertEqual(calls["count"], 1)
        self.assertFalse(result.success)
        self.assertEqual(result.status, GENERATION_INVALID_REQUEST)

    def test_bad_gateway_retried_up_to_max_retries_then_fails(self) -> None:
        client = self._client(max_retries=1)
        calls = {"count": 0}

        def _create(**kwargs):
            calls["count"] += 1
            raise groq.InternalServerError("bad gateway", response=_response(502), body=None)

        client._client.chat.completions.create = _create  # type: ignore[attr-defined]

        with patch("time.sleep", return_value=None):
            result = client.generate("system", "user")

        # Initial attempt + 1 configured retry = 2 calls total, then gives up.
        self.assertEqual(calls["count"], 2)
        self.assertFalse(result.success)
        self.assertTrue(result.retryable)

    def test_gateway_timeout_status_is_retried(self) -> None:
        client = self._client(max_retries=1)
        calls = {"count": 0}

        def _create(**kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise groq.APIStatusError("gateway timeout", response=_response(504), body=None)
            return _fake_completion()

        client._client.chat.completions.create = _create  # type: ignore[attr-defined]

        with patch("time.sleep", return_value=None):
            result = client.generate("system", "user")

        self.assertEqual(calls["count"], 2)
        self.assertTrue(result.success)

    def test_unauthorized_is_never_retried(self) -> None:
        client = self._client(max_retries=2)
        calls = {"count": 0}

        def _create(**kwargs):
            calls["count"] += 1
            raise groq.AuthenticationError("bad api key", response=_response(401), body=None)

        client._client.chat.completions.create = _create  # type: ignore[attr-defined]

        with patch("time.sleep", return_value=None):
            result = client.generate("system", "user")

        self.assertEqual(calls["count"], 1)
        self.assertFalse(result.success)
        self.assertFalse(result.retryable)


if __name__ == "__main__":
    unittest.main()
