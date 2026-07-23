"""Retrieval: embed a question, search the vector store, select context.

Given a user question and a repository URL, returns the most relevant knowledge
chunks (already filtered to that repository) plus a concatenated context block
capped by a character budget so the prompt stays bounded.

Synchronous (embedding + Qdrant are sync); async callers use
``run_in_threadpool``. On-demand indexing when nothing is found is handled one
layer up (in the use case) to avoid an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.exceptions import RagDisabledError
from app.infrastructure.rag import embedder, vector_store

# Upper bound on the assembled context so a large report can't blow the prompt.
_CONTEXT_CHAR_BUDGET = 6000


@dataclass(frozen=True)
class RetrievalResult:
    context: str
    chunks: list[dict[str, Any]]

    @property
    def is_empty(self) -> bool:
        return not self.chunks


def retrieve(question: str, repository_url: str, top_k: int | None = None) -> RetrievalResult:
    """Return ranked knowledge chunks + a bounded context block for a repo.

    Raises :class:`RagDisabledError` when the retrieval stack is switched off.
    This is the single chokepoint every chat path funnels through, so guarding
    it here means the embedding model and vector store are never touched — the
    packages need not even be installed.
    """
    if not settings.rag_enabled:
        raise RagDisabledError()

    limit = top_k or settings.rag_top_k
    query_vector = embedder.embed_query(question)
    hits = vector_store.search(query_vector, repository_url, limit)

    selected: list[dict[str, Any]] = []
    parts: list[str] = []
    used = 0
    for hit in hits:
        text = str(hit.get("text") or "").strip()
        if not text:
            continue
        chunk_type = str(hit.get("chunk_type") or "section")
        block = f"[{chunk_type}]\n{text}"
        if used + len(block) > _CONTEXT_CHAR_BUDGET and parts:
            break
        parts.append(block)
        selected.append(hit)
        used += len(block)

    return RetrievalResult(context="\n\n".join(parts), chunks=selected)
