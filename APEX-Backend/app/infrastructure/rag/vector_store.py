"""Embedded Qdrant vector store for repository knowledge.

All repositories share a single collection (``repo_knowledge``); isolation is
achieved with a payload filter on ``repository_url`` rather than a collection
per repository, so the store scales to thousands of repositories without
collection sprawl.

Point IDs are deterministic (``uuid5`` of repository_url + chunk_type + index)
so re-indexing a repository upserts over its existing points instead of
duplicating them. Runs in embedded mode (persists to disk under
``settings.qdrant_path``) — swap ``QdrantClient(path=...)`` for
``QdrantClient(url=...)`` here to move to a Qdrant server, with no other change.

Qdrant's Python client is synchronous; async callers should use
``run_in_threadpool``.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

from app.core.config import settings

# Stable namespace so the same (repo, chunk_type, index) always maps to the
# same point id across processes/runs.
_ID_NAMESPACE = uuid.UUID("6f0a2e4c-2b7d-4c9a-9f3e-0d1a2b3c4d5e")

_client = None
_client_lock = threading.Lock()
_collection_ready = False


def _get_client():
    """Return the shared embedded QdrantClient, creating it on first use."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from qdrant_client import QdrantClient

                settings.qdrant_path.mkdir(parents=True, exist_ok=True)
                _client = QdrantClient(path=str(settings.qdrant_path))
    return _client


def _ensure_collection(vector_size: int) -> None:
    """Create the shared collection + a payload index on repository_url once."""
    global _collection_ready
    if _collection_ready:
        return
    from qdrant_client import models

    client = _get_client()
    existing = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=models.VectorParams(
                size=vector_size, distance=models.Distance.COSINE
            ),
        )
        # Keyword index makes the per-repository filter fast at scale.
        client.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name="repository_url",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
    _collection_ready = True


def point_id(repository_url: str, chunk_type: str, index: int) -> str:
    """Deterministic point id so re-index upserts rather than duplicates."""
    return str(uuid.uuid5(_ID_NAMESPACE, f"{repository_url}|{chunk_type}|{index}"))


def delete_repository(repository_url: str) -> None:
    """Remove every point belonging to a repository (used before re-index)."""
    from qdrant_client import models

    client = _get_client()
    existing = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection not in existing:
        return
    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="repository_url",
                        match=models.MatchValue(value=repository_url),
                    )
                ]
            )
        ),
    )


def upsert(vectors: list[list[float]], payloads: list[dict[str, Any]], ids: list[str]) -> None:
    """Insert or overwrite points. All three lists must be the same length."""
    if not vectors:
        return
    from qdrant_client import models

    _ensure_collection(len(vectors[0]))
    client = _get_client()
    points = [
        models.PointStruct(id=pid, vector=vector, payload=payload)
        for pid, vector, payload in zip(ids, vectors, payloads)
    ]
    client.upsert(collection_name=settings.qdrant_collection, points=points)


def search(query_vector: list[float], repository_url: str, top_k: int) -> list[dict[str, Any]]:
    """Return the top-K payloads for a repository, ranked by similarity."""
    from qdrant_client import models

    client = _get_client()
    existing = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection not in existing:
        return []
    response = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="repository_url",
                    match=models.MatchValue(value=repository_url),
                )
            ]
        ),
        limit=top_k,
        with_payload=True,
    )
    results: list[dict[str, Any]] = []
    for hit in response.points:
        payload = dict(hit.payload or {})
        payload["_score"] = hit.score
        results.append(payload)
    return results


def list_repositories() -> list[dict[str, Any]]:
    """Return the distinct indexed repositories (url + name + metadata)."""
    client = _get_client()
    existing = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection not in existing:
        return []

    seen: dict[str, dict[str, Any]] = {}
    next_offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=settings.qdrant_collection,
            limit=256,
            offset=next_offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            url = payload.get("repository_url")
            if url and url not in seen:
                seen[url] = {
                    "repository_url": url,
                    "repository_name": payload.get("repository_name"),
                    "project_type": payload.get("project_type"),
                    "java_version": payload.get("java_version"),
                    "framework": payload.get("framework"),
                    "job_id": payload.get("job_id"),
                    "analysis_timestamp": payload.get("analysis_timestamp"),
                }
        if next_offset is None:
            break
    return list(seen.values())
