"""Streaming chat client for a local Ollama server (fallback LLM).

Used only when Groq is unavailable. Ollama streams newline-delimited JSON
objects (not SSE) from ``POST /api/chat``; each object carries a
``message.content`` delta. No API key is required — availability is simply
whether the local server responds.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import settings
from app.core.exceptions import ChatLLMServiceError


class OllamaClient:
    provider = "ollama"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_model
        self._timeout = timeout or settings.chat_llm_request_timeout_seconds

    async def stream_chat(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        """Yield answer text deltas from Ollama. Raises on transport errors."""
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
            "options": {"temperature": 0.2},
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST", f"{self._base_url}/api/chat", json=payload
                ) as response:
                    if response.status_code != 200:
                        await response.aread()
                        raise ChatLLMServiceError(
                            f"Ollama server returned HTTP {response.status_code}."
                        )
                    async for line in response.aiter_lines():
                        delta = _parse_ndjson_delta(line)
                        if delta:
                            yield delta
        except httpx.HTTPError as exc:  # server not running / timeout
            raise ChatLLMServiceError("Local Ollama server could not be reached.") from exc


def _parse_ndjson_delta(line: str) -> str | None:
    """Extract the content delta from one Ollama NDJSON line."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    return (obj.get("message") or {}).get("content") or None
