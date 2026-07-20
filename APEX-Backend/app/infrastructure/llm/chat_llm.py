"""Chat LLM facade with Groq (primary) -> Ollama (fallback) streaming.

Exposes a single ``stream_chat`` async generator that yields plain text deltas.
Groq is tried first when configured; if it fails *before emitting any token*
(not configured, transport error, HTTP error), streaming falls through to a
local Ollama server. A failure *after* tokens have already been streamed is
surfaced rather than silently retried, to avoid emitting duplicated content.

``last_provider`` records which provider actually produced the answer, for the
final event's details.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.core.exceptions import ChatLLMNotConfiguredError, ChatLLMServiceError
from app.infrastructure.llm.groq_client import GroqClient
from app.infrastructure.llm.ollama_client import OllamaClient


class ChatLLM:
    def __init__(
        self,
        groq_client: GroqClient | None = None,
        ollama_client: OllamaClient | None = None,
    ) -> None:
        self._groq = groq_client or GroqClient()
        self._ollama = ollama_client or OllamaClient()
        self.last_provider: str | None = None

    async def stream_chat(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        # Groq only if it has a key; Ollama is always the last resort.
        providers = []
        if self._groq.is_configured:
            providers.append(self._groq)
        providers.append(self._ollama)

        last_error: Exception | None = None
        for provider in providers:
            started = False
            try:
                async for delta in provider.stream_chat(system_prompt, user_prompt):
                    if not started:
                        started = True
                        self.last_provider = provider.provider
                    yield delta
                # Completed without error (possibly empty) — done.
                if not started:
                    self.last_provider = provider.provider
                return
            except (ChatLLMNotConfiguredError, ChatLLMServiceError) as exc:
                last_error = exc
                if started:
                    # Partial content already streamed; a fallback would repeat it.
                    raise
                continue  # try the next provider

        raise last_error or ChatLLMNotConfiguredError()
