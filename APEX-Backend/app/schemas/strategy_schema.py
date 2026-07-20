"""Request/response schemas for the Strategy chatbot (JavaApex Assistant).

Field names match exactly what the existing chat widget sends/expects
(``repo_url``, ``question``, ``strategy_context`` for queries; ``answer`` /
``rationale`` / ``details`` for the non-streaming response).
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class StrategyQueryRequest(BaseModel):
    """Body for ``POST /api/strategy/query`` and ``.../query/stream``."""

    question: str
    repo_url: Optional[str] = None
    # The widget sends a rich, pre-built page context; kept loosely typed since
    # it is supplementary grounding, not a strict contract.
    strategy_context: Optional[dict[str, Any]] = None
    provider: Optional[str] = None  # accepted for compatibility; routing is automatic


class StrategyAnswerResponse(BaseModel):
    """Non-streaming success body — matches the frontend ``StrategyAnswerResponse``."""

    answer: str
    rationale: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class IndexRequest(BaseModel):
    """Body for ``POST /api/strategy/index`` and ``.../reindex``.

    Provide a ``job_id`` (indexes that job's report) or a ``repo_url`` (indexes
    the newest analyzed report for that repository).
    """

    job_id: Optional[str] = None
    repo_url: Optional[str] = None


class IndexResponse(BaseModel):
    status: str = "INDEXED"
    repository_url: str
    repository_name: Optional[str] = None
    job_id: Optional[str] = None
    chunk_count: int


class RepositorySummary(BaseModel):
    repository_url: str
    repository_name: Optional[str] = None
    project_type: Optional[str] = None
    java_version: Optional[str] = None
    framework: Optional[str] = None
    job_id: Optional[str] = None
    analysis_timestamp: Optional[str] = None


class RepositoriesResponse(BaseModel):
    repositories: list[RepositorySummary] = Field(default_factory=list)
