"""Request/response schemas for the Target Java Version Recommendation endpoint."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class JavaVersionRecommendationRequest(BaseModel):
    """Body for ``POST /api/java-version-recommendation``.

    Field names match what the frontend's Strategy step already sends (source
    version + metadata detected fresh by Discovery moments earlier).
    """

    source_java_version: str
    detected_java_version: Optional[str] = None
    build_tool: Optional[str] = None
    dependencies: list[dict[str, Any]] = Field(default_factory=list)
    has_tests: bool = False
    api_endpoint_count: int = 0
    risk_level: Optional[str] = None
    llm_provider: Optional[str] = None  # accepted for backward compatibility; always served via Hugging Face


class AlternativeOption(BaseModel):
    version: str
    risk: Optional[str] = None
    reason: Optional[str] = None


class JavaVersionRecommendationResponse(BaseModel):
    """Success body for ``POST /api/java-version-recommendation``."""

    recommended_target_version: str
    recommended_versions: list[str] = Field(default_factory=list)
    confidence: str
    rationale: list[str]
    benefits: list[str] = Field(default_factory=list)
    compatibility_considerations: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    alternative_options: list[AlternativeOption] = Field(default_factory=list)
    provider_used: str = "huggingface"
    already_at_latest_supported_version: bool = False
    raw_recommendation: Optional[dict[str, Any]] = None
