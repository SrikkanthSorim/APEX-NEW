"""Sentence-embedding wrapper around ``BAAI/bge-small-en-v1.5``.

The model (384-dim) is loaded lazily and cached as a module-level singleton so
the (multi-hundred-MB) weights are read once per process, not per request.
Embedding is CPU-bound and synchronous; callers on the async path should run
these methods via ``run_in_threadpool``.

BGE models expect a short instruction prefix on *queries* (but not on the
indexed documents), which measurably improves retrieval — that asymmetry is
handled here so callers don't have to remember it.
"""

from __future__ import annotations

import threading

from app.core.config import settings

# BGE's recommended retrieval instruction, prepended to queries only.
_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

_model = None
_model_lock = threading.Lock()


def _get_model():
    """Load (once) and return the shared SentenceTransformer model."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                # Imported lazily so importing this module (e.g. at app startup)
                # never triggers the heavy torch/transformers import chain until
                # embeddings are actually needed.
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(settings.embedding_model_name)
    return _model


def embedding_dimension() -> int:
    """Vector size produced by the configured model (384 for bge-small)."""
    return int(_get_model().get_sentence_embedding_dimension())


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed indexed knowledge chunks (no query instruction prefix)."""
    if not texts:
        return []
    vectors = _get_model().encode(
        texts, normalize_embeddings=True, show_progress_bar=False
    )
    return [vector.tolist() for vector in vectors]


def embed_query(text: str) -> list[float]:
    """Embed a user question (with the BGE query instruction prefix)."""
    vector = _get_model().encode(
        _QUERY_INSTRUCTION + text,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vector.tolist()
