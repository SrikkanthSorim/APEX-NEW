"""Start Migration + polling endpoints.

Thin controller: validates + kicks off the async migration (transform + push)
and exposes summary/detail/logs for the Result page to poll. No migration or git
logic lives here.
"""

from __future__ import annotations

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from app.application.pipelines.migration_execution_pipeline import MigrationExecutionPipeline
from app.core.exceptions import MigrationConfigError, MigrationExecutionError, MigrationJobNotFoundError
from app.schemas.migration_execution_schema import MigrationStartRequest

router = APIRouter(tags=["migration"])

_pipeline = MigrationExecutionPipeline()


def _not_found_response() -> JSONResponse:
    # Shape matches the frontend's special handling (ApiError.code check).
    return JSONResponse(
        status_code=404,
        content={
            "detail": {
                "code": "MIGRATION_JOB_NOT_FOUND",
                "message": "Migration status is no longer available.",
            }
        },
    )


@router.post(
    "/migration/{job_id}/start",
    summary="Start the migration and publish the result.",
)
async def start_migration(
    job_id: str,
    payload: MigrationStartRequest | None = Body(default=None),
) -> JSONResponse:
    request = payload.model_dump() if payload else None
    try:
        result = _pipeline.start(job_id, request)
    except (MigrationConfigError, MigrationExecutionError) as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content={"jobId": job_id, "status": exc.status, "message": exc.message},
        )
    return JSONResponse(status_code=200, content=result)


@router.get("/migration/{job_id}/summary", summary="Migration status summary (polled).")
async def migration_summary(job_id: str) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=_pipeline.get_summary(job_id))
    except MigrationJobNotFoundError:
        return _not_found_response()


@router.get("/migration/{job_id}/detail", summary="Full migration result.")
async def migration_detail(job_id: str) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=_pipeline.get_detail(job_id))
    except MigrationJobNotFoundError:
        return _not_found_response()


@router.get("/migration/{job_id}/logs", summary="Migration log lines.")
async def migration_logs(job_id: str) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=_pipeline.get_logs(job_id))
    except MigrationJobNotFoundError:
        return _not_found_response()


@router.get("/migration/{job_id}/fossa", summary="FOSSA dependency/license scan results.")
async def migration_fossa(job_id: str) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=_pipeline.get_fossa(job_id))
    except MigrationJobNotFoundError:
        return _not_found_response()
