"""Discovery endpoint.

Thin controller: receives the request, delegates to the DiscoveryPipeline
(run off the event loop), and returns the response. No clone or analyzer logic
lives here.
"""

from __future__ import annotations

from fastapi import APIRouter, Body
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.application.pipelines.discovery_pipeline import DiscoveryPipeline
from app.core.exceptions import DiscoveryError
from app.schemas.discovery_schema import DiscoveryRequest, DiscoveryResponse

router = APIRouter(tags=["discovery"])

_pipeline = DiscoveryPipeline()


@router.post(
    "/discovery/{job_id}",
    response_model=DiscoveryResponse,
    summary="Clone and analyze a connected repository (Discovery stage).",
)
async def run_discovery(
    job_id: str,
    payload: DiscoveryRequest | None = Body(default=None),
) -> JSONResponse:
    """Clone the connected repository and analyze the project.

    Read-only after cloning — no migration, build, or file modification happens.
    """
    token = payload.github_token if payload else None
    try:
        outcome = await run_in_threadpool(_pipeline.run, job_id, token)
    except DiscoveryError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "jobId": job_id,
                "status": exc.status,
                "message": exc.message,
            },
        )

    return JSONResponse(status_code=200, content=outcome.response)
