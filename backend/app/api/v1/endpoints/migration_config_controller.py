"""Migration Config endpoint.

Thin controller: validates + persists the migration destination/options via the
MigrationConfigPipeline. No repo creation or push happens here.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.application.pipelines.migration_config_pipeline import MigrationConfigPipeline
from app.core.exceptions import MigrationConfigError
from app.schemas.migration_config_schema import (
    MigrationConfigRequest,
    MigrationConfigResponse,
)

router = APIRouter(tags=["migration-config"])

_pipeline = MigrationConfigPipeline()


@router.post(
    "/migration-config/{job_id}",
    response_model=MigrationConfigResponse,
    summary="Save the migration destination and options (Migration Config stage).",
)
async def save_migration_config(job_id: str, payload: MigrationConfigRequest) -> JSONResponse:
    """Persist the migration configuration for the job.

    Only stores the config (destination + options). Repo creation and push are
    deferred to the Start Migration stage.
    """
    config = payload.model_dump(by_alias=True)
    try:
        outcome = _pipeline.run(job_id, config)
    except MigrationConfigError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "jobId": job_id,
                "status": exc.status,
                "message": exc.message,
            },
        )

    return JSONResponse(status_code=200, content=outcome.response)
