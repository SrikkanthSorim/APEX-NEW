"""Target Java Version Recommendation use case (Hugging Face LLM-backed).

The LLM decides the *reasoning* (why, benefits, compatibility considerations,
confidence, alternatives) - nothing here fabricates that content. The only
thing this layer enforces deterministically is the hard product invariant
that the recommended version must be a real, supported release strictly
higher than the detected source version (or, if the source is already the
newest supported release, that same version) - if the model ever returns
something outside the allowed set, it is clamped to the closest allowed
option rather than trusted blindly.
"""

from __future__ import annotations

import re

from app.core.exceptions import InvalidJavaVersionError, LLMResponseInvalidError
from app.infrastructure.llm.huggingface_client import HuggingFaceClient
from app.infrastructure.llm.prompt_templates import (
    JAVA_VERSION_RECOMMENDATION_SYSTEM_PROMPT,
    build_java_version_recommendation_prompt,
)
from app.schemas.java_version_schema import JavaVersionRecommendationRequest

# Canonical, LTS-first release ladder. Matches the frontend's dropdown/LTS set
# so every recommended version can actually be selected and rendered.
_LTS_LADDER = ["8", "11", "17", "21", "25"]


def _parse_major_version(raw: str) -> int:
    match = re.search(r"\d+", raw or "")
    if not match:
        raise InvalidJavaVersionError()
    return int(match.group(0))


def _allowed_targets(source_major: int) -> tuple[list[str], bool]:
    """Return (allowed target versions, already_at_latest)."""
    higher = [v for v in _LTS_LADDER if int(v) > source_major]
    if higher:
        return higher, False
    # Source is already at/above the newest LTS this platform tracks -
    # recommend staying, per product spec.
    latest = _LTS_LADDER[-1]
    return [str(max(source_major, int(latest)))], True


class RecommendJavaVersionUseCase:
    def __init__(self, llm_client: HuggingFaceClient | None = None) -> None:
        self._llm = llm_client or HuggingFaceClient()

    async def execute(self, request: JavaVersionRecommendationRequest) -> dict:
        source_major = _parse_major_version(request.source_java_version)
        allowed_targets, already_at_latest = _allowed_targets(source_major)

        system_prompt = JAVA_VERSION_RECOMMENDATION_SYSTEM_PROMPT
        user_prompt = build_java_version_recommendation_prompt(
            source_java_version=str(source_major),
            build_tool=request.build_tool,
            dependencies=request.dependencies,
            has_tests=request.has_tests,
            api_endpoint_count=request.api_endpoint_count,
            risk_level=request.risk_level,
            allowed_target_versions=allowed_targets,
            already_at_latest=already_at_latest,
        )

        raw = await self._llm.chat_json(system_prompt, user_prompt)
        return self._sanitize(raw, allowed_targets, already_at_latest)

    @staticmethod
    def _sanitize(raw: dict, allowed_targets: list[str], already_at_latest: bool) -> dict:
        rationale = [str(item).strip() for item in raw.get("rationale") or [] if str(item).strip()]
        if not rationale:
            raise LLMResponseInvalidError("The model did not provide a rationale for its recommendation.")

        recommended = str(raw.get("recommended_target_version") or "").strip()
        # Extract the leading integer in case the model returns "Java 21" etc.
        match = re.search(r"\d+", recommended)
        recommended = match.group(0) if match else ""
        if recommended not in allowed_targets:
            # The model didn't follow instructions - fall back to the lowest
            # (safest/most conservative) allowed target rather than trusting
            # an out-of-range value.
            recommended = allowed_targets[0]

        confidence = str(raw.get("confidence") or "").strip().title()
        if confidence not in ("High", "Medium", "Low"):
            confidence = "Medium"

        benefits = [str(item).strip() for item in raw.get("benefits") or [] if str(item).strip()]
        compatibility_considerations = [
            str(item).strip() for item in raw.get("compatibility_considerations") or [] if str(item).strip()
        ]

        alternative_versions = [v for v in allowed_targets if v != recommended]
        raw_alternative_options = raw.get("alternative_options") or []
        options_by_version: dict[str, dict] = {}
        if isinstance(raw_alternative_options, list):
            for item in raw_alternative_options:
                if not isinstance(item, dict):
                    continue
                version_match = re.search(r"\d+", str(item.get("version") or ""))
                version = version_match.group(0) if version_match else ""
                if version in alternative_versions:
                    options_by_version[version] = {
                        "version": version,
                        "risk": str(item.get("risk") or "").strip() or None,
                        "reason": str(item.get("reason") or "").strip() or None,
                    }
        alternative_options = [
            options_by_version.get(version, {"version": version, "risk": None, "reason": None})
            for version in alternative_versions
        ]

        return {
            "recommended_target_version": recommended,
            "recommended_versions": [recommended, *alternative_versions],
            "confidence": confidence,
            "rationale": rationale,
            "benefits": benefits,
            "compatibility_considerations": compatibility_considerations,
            "alternatives": alternative_versions,
            "alternative_options": alternative_options,
            "provider_used": "huggingface",
            "already_at_latest_supported_version": already_at_latest,
            "raw_recommendation": raw,
        }
