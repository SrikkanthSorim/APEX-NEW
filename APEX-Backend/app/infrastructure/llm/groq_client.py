"""Streaming chat client for Groq (primary LLM for the Strategy chatbot).

Groq exposes an OpenAI-compatible chat completions API, so this is a thin
``httpx`` streaming wrapper (no extra SDK) that mirrors the style of
``huggingface_client``. Yields plain text token deltas as they arrive.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import settings
from app.core.exceptions import ChatLLMNotConfiguredError, ChatLLMServiceError


class GroqClient:
    provider = "groq"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._api_key = (api_key if api_key is not None else settings.groq_api_key).strip()
        self._base_url = (base_url or settings.groq_base_url).rstrip("/")
        self._model = model or settings.groq_model
        self._timeout = timeout or settings.chat_llm_request_timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def stream_chat(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        """Yield answer text deltas from Groq. Raises on config/transport errors."""
        if not self._api_key:
            raise ChatLLMNotConfiguredError()

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        await response.aread()
                        raise ChatLLMServiceError(
                            f"Groq API returned HTTP {response.status_code}."
                        )
                    async for line in response.aiter_lines():
                        delta = _parse_sse_delta(line)
                        if delta:
                            yield delta
        except httpx.HTTPError as exc:  # transport / timeout / DNS
            raise ChatLLMServiceError("Groq API could not be reached.") from exc


def _parse_sse_delta(line: str) -> str | None:
    """Extract the incremental content from one OpenAI-style SSE line."""
    line = line.strip()
    if not line or not line.startswith("data:"):
        return None
    data = line[len("data:"):].strip()
    if not data or data == "[DONE]":
        return None
    try:
        chunk = json.loads(data)
        return chunk["choices"][0]["delta"].get("content") or None
    except (ValueError, KeyError, IndexError, TypeError):
        return None
