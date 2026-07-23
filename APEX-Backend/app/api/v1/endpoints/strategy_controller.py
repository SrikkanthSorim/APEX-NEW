"""Strategy chatbot (JavaApex Assistant) endpoints — mounted at ``/api``.

The Strategy chat widget calls these unversioned paths directly:
  * ``POST /api/strategy/query/stream`` — SSE stream (phase/chunk/final/error).
  * ``POST /api/strategy/query``        — non-streaming twin.
  * ``POST /api/strategy/index``        — build+upsert vectors for a job/repo.
  * ``POST /api/strategy/reindex``      — replace a repository's vectors.
  * ``GET  /api/strategy/repositories`` — list indexed repositories.

The SSE frame shape (``event:``/``data:`` JSON, ``\n\n``-separated) matches the
widget's ``flushEvent`` parser exactly — do not change it without updating the
frontend.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

from app.application.use_cases.answer_repo_question import AnswerRepoQuestionUseCase
from app.application.use_cases.index_repository import (
    IndexRepositoryUseCase,
    RepositoryNotFoundForIndexingError,
)
from app.core.config import settings
from app.core.exceptions import RagDisabledError, RepositoryNotIndexedError, StrategyChatError
from app.infrastructure.rag import vector_store
from app.schemas.strategy_schema import (
    IndexRequest,
    IndexResponse,
    RepositoriesResponse,
    StrategyAnswerResponse,
    StrategyQueryRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategy", tags=["strategy"])

_answer_use_case = AnswerRepoQuestionUseCase()
_index_use_case = IndexRepositoryUseCase()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Disable proxy buffering so events flush immediately.
    "X-Accel-Buffering": "no",
}


def _sse(event: str, payload: dict) -> str:
    """Format a single SSE frame the widget's parser understands."""
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@router.post("/query/stream")
async def query_stream(payload: StrategyQueryRequest) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        try:
            yield _sse("phase", {"message": "Reading strategy page"})
            prepared = await _answer_use_case.prepare(
                question=payload.question,
                repository_url=payload.repo_url,
                page_context=payload.strategy_context,
            )

            yield _sse("phase", {"message": "Preparing answer"})
            buffer: list[str] = []
            async for delta in _answer_use_case.stream(prepared):
                buffer.append(delta)
                yield _sse("chunk", {"chunk": delta})

            answer = "".join(buffer).strip()
            yield _sse(
                "final",
                {
                    "parsed": {"answer": answer, "rationale": []},
                    "details": {
                        "provider_used": prepared.chat.last_provider,
                        "repository": prepared.repository_metadata,
                        "retrieved_chunk_types": prepared.retrieved_chunk_types,
                    },
                },
            )
        except StrategyChatError as exc:
            yield _sse("error", {"message": exc.message, "status": exc.status})
        except Exception:  # noqa: BLE001 - surface a clean error, never a 500 stream
            logger.exception("Strategy chat stream failed.")
            yield _sse(
                "error",
                {"message": "The assistant hit an unexpected error. Please try again."},
            )

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS
    )


@router.post("/query", response_model=StrategyAnswerResponse)
async def query(payload: StrategyQueryRequest) -> JSONResponse:
    try:
        result = await _answer_use_case.answer(
            question=payload.question,
            repository_url=payload.repo_url,
            page_context=payload.strategy_context,
        )
    except StrategyChatError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content={"status": exc.status, "message": exc.message, "detail": exc.message},
        )
    return JSONResponse(status_code=200, content=result)


@router.post("/index", response_model=IndexResponse)
async def index(payload: IndexRequest) -> JSONResponse:
    return await _run_index(payload)


@router.post("/reindex", response_model=IndexResponse)
async def reindex(payload: IndexRequest) -> JSONResponse:
    # index_report already deletes existing points first, so reindex == index.
    return await _run_index(payload)


async def _run_index(payload: IndexRequest) -> JSONResponse:
    # Indexing goes straight to the embedder/vector store without passing
    # through retriever.retrieve(), so it needs its own guard — otherwise this
    # is the one path that would surface a raw ImportError as a 500.
    if not settings.rag_enabled:
        exc = RagDisabledError()
        return JSONResponse(
            status_code=exc.http_status,
            content={"status": exc.status, "message": exc.message, "detail": exc.message},
        )
    try:
        if payload.job_id:
            outcome = await run_in_threadpool(_index_use_case.index_by_job_id, payload.job_id)
        elif payload.repo_url:
            outcome = await run_in_threadpool(_index_use_case.index_by_repo_url, payload.repo_url)
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "INVALID_REQUEST",
                    "message": "Provide either job_id or repo_url.",
                    "detail": "Provide either job_id or repo_url.",
                },
            )
    except RepositoryNotFoundForIndexingError:
        message = "Repository has not been analyzed yet. Run discovery for it first."
        return JSONResponse(
            status_code=404,
            content={"status": "REPOSITORY_NOT_FOUND", "message": message, "detail": message},
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "INDEXED",
            "repository_url": outcome.repository_url,
            "repository_name": outcome.repository_name,
            "job_id": outcome.job_id,
            "chunk_count": outcome.chunk_count,
        },
    )


@router.get("/repositories", response_model=RepositoriesResponse)
async def repositories() -> JSONResponse:
    # Unlike the chat endpoints there is no StrategyChatError path here, so the
    # disabled case is handled directly: an empty list is the honest answer
    # (nothing is indexed) and keeps the widget rendering instead of 500ing on
    # a missing qdrant-client import.
    if not settings.rag_enabled:
        return JSONResponse(status_code=200, content={"repositories": []})
    repos = await run_in_threadpool(vector_store.list_repositories)
    return JSONResponse(status_code=200, content={"repositories": repos})
