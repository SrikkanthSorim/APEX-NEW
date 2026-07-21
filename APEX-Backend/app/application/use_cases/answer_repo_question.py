"""Answer a repository question with retrieval-augmented generation.

Orchestrates the RAG pipeline: retrieve the most relevant knowledge chunks for
the repository (indexing on demand if the repo was analyzed but never indexed),
build a grounded prompt, then stream the answer from the chat LLM (Groq ->
Ollama). Retrieval is CPU-bound and runs in a threadpool; generation is async.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from fastapi.concurrency import run_in_threadpool

from app.application.use_cases.index_repository import (
    IndexRepositoryUseCase,
    RepositoryNotFoundForIndexingError,
)
from app.core.exceptions import RepositoryNotIndexedError
from app.infrastructure.llm.chat_llm import ChatLLM
from app.infrastructure.rag import prompt_builder, retriever
from app.shared import branding


@dataclass
class PreparedAnswer:
    system_prompt: str
    user_prompt: str
    repository_metadata: dict[str, Any]
    retrieved_chunk_types: list[str] = field(default_factory=list)
    chat: ChatLLM = field(default_factory=ChatLLM)


class AnswerRepoQuestionUseCase:
    def __init__(self, indexer: IndexRepositoryUseCase | None = None) -> None:
        self._indexer = indexer or IndexRepositoryUseCase()

    async def prepare(
        self,
        *,
        question: str,
        repository_url: str | None,
        page_context: dict[str, Any] | None = None,
    ) -> PreparedAnswer:
        """Retrieve context (indexing on demand) and build grounded prompts."""
        repo_url = (repository_url or "").strip()
        if not repo_url:
            raise RepositoryNotIndexedError(
                "A repository URL is required to answer questions about it."
            )

        result = await run_in_threadpool(retriever.retrieve, question, repo_url)

        if result.is_empty:
            # Analyzed but never indexed? Index on demand, then retry once.
            try:
                await run_in_threadpool(self._indexer.index_by_repo_url, repo_url)
            except RepositoryNotFoundForIndexingError as exc:
                raise RepositoryNotIndexedError() from exc
            result = await run_in_threadpool(retriever.retrieve, question, repo_url)
            if result.is_empty:
                raise RepositoryNotIndexedError()

        repository_metadata = _metadata_from(result.chunks, page_context, repo_url)
        user_prompt = prompt_builder.build_user_prompt(
            question=question,
            retrieved_context=result.context,
            repository_metadata=repository_metadata,
            page_context=page_context,
        )
        return PreparedAnswer(
            system_prompt=prompt_builder.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            repository_metadata=repository_metadata,
            retrieved_chunk_types=[str(c.get("chunk_type")) for c in result.chunks],
        )

    async def stream(self, prepared: PreparedAnswer) -> AsyncIterator[str]:
        """Yield answer text deltas for a prepared question.

        Deltas are passed through the branding sanitizer as a final guard so no
        internal tooling / recipe identifier can reach the user even if the model
        echoes one from its own knowledge.
        """
        raw_deltas = prepared.chat.stream_chat(
            prepared.system_prompt, prepared.user_prompt
        )
        async for delta in branding.sanitize_stream(raw_deltas):
            yield delta

    async def answer(
        self,
        *,
        question: str,
        repository_url: str | None,
        page_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Non-streaming variant: collect the full answer and return it."""
        prepared = await self.prepare(
            question=question, repository_url=repository_url, page_context=page_context
        )
        parts = [delta async for delta in self.stream(prepared)]
        return {
            "answer": "".join(parts).strip(),
            "rationale": [],
            "details": {
                "provider_used": prepared.chat.last_provider,
                "repository": prepared.repository_metadata,
                "retrieved_chunk_types": prepared.retrieved_chunk_types,
            },
        }


def _metadata_from(
    chunks: list[dict[str, Any]],
    page_context: dict[str, Any] | None,
    repo_url: str,
) -> dict[str, Any]:
    """Prefer indexed metadata; fall back to the live page context."""
    payload = chunks[0] if chunks else {}
    repo_ctx = (page_context or {}).get("repository") or {}
    return {
        "repository_url": payload.get("repository_url") or repo_ctx.get("url") or repo_url,
        "repository_name": payload.get("repository_name") or repo_ctx.get("name"),
        "project_type": payload.get("project_type"),
        "java_version": payload.get("java_version"),
        "framework": payload.get("framework") or repo_ctx.get("language"),
    }
