"""Connect endpoint.

The controller is intentionally thin: it receives the request, delegates to the
:class:`ConnectPipeline`, and shapes the response. It contains no GitHub logic.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.application.pipelines.connect_pipeline import ConnectPipeline
from app.core.exceptions import ConnectError
from app.schemas.connect_schema import ConnectRequest, ConnectResponse
from app.shared.response_builder import build_connect_error, build_connect_success

router = APIRouter(tags=["connect"])

_pipeline = ConnectPipeline()


@router.post(
    "/connect",
    response_model=ConnectResponse,
    summary="Validate a GitHub repository and create a migration job.",
)
async def connect_repository(payload: ConnectRequest) -> JSONResponse:
    """Validate the repository URL, detect visibility/access, and create a job.

    No cloning or migration happens here — this only verifies access and stores
    the connect report.
    """
    try:
        result = await _pipeline.run(payload.repo_url, payload.github_token)
    except ConnectError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content=build_connect_error(
                access_status=exc.access_status,
                message=exc.message,
            ),
        )

    return JSONResponse(
        status_code=200,
        content=build_connect_success(
            job_id=result.job_id,
            repo_url=result.repo_url,
            owner=result.owner,
            repo_name=result.repo_name,
            repo_visibility=result.repo_visibility,
            access_status=result.access_status,
            message=result.message,
        ),
    )
