"""Scenario: the underlying Groq HTTP call never returns at all (a stalled
DNS lookup or a black-holed connection that httpx's own request timeout does
not reliably catch). GroqClient must still produce a bounded GENERATION_TIMEOUT
result -- never hang the calling thread forever with no completion/failure/
timeout outcome, which is exactly the symptom this watchdog exists to prevent.
"""

import time
import unittest
from unittest.mock import patch

from app.domain.llm.llm_client import GENERATION_TIMEOUT
from app.infrastructure.llm import groq_client
from app.infrastructure.llm.groq_client import GroqClient


def _hang_forever(**kwargs):
    time.sleep(10)  # far longer than the test's configured timeout below
    raise AssertionError("should never actually complete")


class GroqClientWatchdogTests(unittest.TestCase):
    def test_stalled_call_times_out_instead_of_hanging_forever(self) -> None:
        client = GroqClient(
            api_key="test-key", model="test-model", connect_timeout=0.1, read_timeout=0.2, max_retries=0,
        )
        # Simulate a call that never returns (e.g. a stalled DNS resolution) --
        # httpx's own connect/read timeout is bypassed entirely here on purpose,
        # so only the watchdog's Future.result(timeout=...) can rescue this.
        client._client.chat.completions.create = _hang_forever  # type: ignore[attr-defined]

        started = time.monotonic()
        # Keep the watchdog's slack small so this test doesn't have to wait
        # out the real (production-sized) grace period.
        with patch.object(groq_client, "_WATCHDOG_SLACK_SECONDS", 0.3):
            result = client.generate("system prompt", "user prompt")
        elapsed = time.monotonic() - started

        self.assertFalse(result.success)
        self.assertEqual(result.status, GENERATION_TIMEOUT)
        # Bounded by connect+read timeout + watchdog slack (0.1s + 0.2s +
        # 0.3s), nowhere near the 10s the fake call actually sleeps for --
        # proves the calling thread was handed back control instead of
        # blocking on the abandoned call.
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
