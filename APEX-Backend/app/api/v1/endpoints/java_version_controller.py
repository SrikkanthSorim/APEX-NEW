"""Target Java Version Recommendation endpoint (unversioned - mounted at ``/api``).

The Strategy step calls this immediately after Discovery detects the real
source Java version from the repo's build files. This controller forwards
that detected version + project metadata to a Hugging Face-hosted LLM and
returns a fresh, non-cached recommendation every time.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.application.use_cases.recommend_java_version import RecommendJavaVersionUseCase
from app.core.exceptions import JavaVersionRecommendationError
from app.schemas.java_version_schema import (
    JavaVersionRecommendationRequest,
    JavaVersionRecommendationResponse,
)

router = APIRouter(tags=["java-version-recommendation"])

_use_case = RecommendJavaVersionUseCase()


@router.post(
    "/java-version-recommendation",
    response_model=JavaVersionRecommendationResponse,
    summary="AI-recommend a target Java version, given the detected source version and project metadata.",
)
async def recommend_java_version(payload: JavaVersionRecommendationRequest) -> JSONResponse:
    try:
        result = await _use_case.execute(payload)
    except JavaVersionRecommendationError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content={"status": exc.status, "message": exc.message, "detail": exc.message},
        )

    return JSONResponse(status_code=200, content=result)
