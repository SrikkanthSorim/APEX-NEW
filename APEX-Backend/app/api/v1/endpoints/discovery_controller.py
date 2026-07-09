"""Discovery endpoint.

Thin controller: receives the request, delegates to the DiscoveryPipeline
(run off the event loop), and returns the response. No clone or analyzer logic
lives here.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.application.pipelines.discovery_pipeline import DiscoveryPipeline
from app.application.use_cases.assess_microservice_eligibility import (
    AssessMicroserviceEligibilityUseCase,
)
from app.application.use_cases.browse_repository import RepositoryFileBrowser
from app.core.exceptions import DiscoveryError, RepositoryBrowseError
from app.schemas.discovery_schema import DiscoveryRequest, DiscoveryResponse

router = APIRouter(tags=["discovery"])

_pipeline = DiscoveryPipeline()
_file_browser = RepositoryFileBrowser()
_microservice_use_case = AssessMicroserviceEligibilityUseCase()


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


@router.get(
    "/discovery/{job_id}/files",
    summary="List files/folders in the cloned repository (Discovery workspace).",
)
async def list_discovery_files(
    job_id: str,
    path: str = Query("", description="Folder path relative to the repository root."),
) -> JSONResponse:
    """Lazily list one directory level of the job's already-cloned repo.

    No re-cloning and no GitHub API calls — this reads the ``original-repo``
    clone Discovery already made, so it works for large repos without extra
    round trips (only the currently expanded folder is listed).
    """
    try:
        entries = await run_in_threadpool(_file_browser.list_directory, job_id, path)
    except RepositoryBrowseError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content={"jobId": job_id, "status": exc.status, "message": exc.message},
        )

    return JSONResponse(
        status_code=200,
        content={
            "jobId": job_id,
            "path": path,
            "files": [
                {"name": entry.name, "path": entry.path, "type": entry.type, "size": entry.size, "url": ""}
                for entry in entries
            ],
        },
    )


@router.get(
    "/discovery/{job_id}/file",
    summary="Read a text file's content from the cloned repository (Discovery workspace).",
)
async def get_discovery_file_content(
    job_id: str,
    path: str = Query(..., description="File path relative to the repository root."),
) -> JSONResponse:
    try:
        result = await run_in_threadpool(_file_browser.read_file, job_id, path)
    except RepositoryBrowseError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content={"jobId": job_id, "status": exc.status, "message": exc.message},
        )

    return JSONResponse(
        status_code=200,
        content={
            "jobId": job_id,
            "filePath": result.path,
            "content": result.content,
            "size": result.size,
        },
    )


@router.get(
    "/discovery/{job_id}/microservice-eligibility",
    summary="Assess microservice eligibility from the cloned repository (Discovery workspace).",
)
async def get_microservice_eligibility(job_id: str) -> JSONResponse:
    """Real static analysis over the job's cloned repo.

    Detects controllers/services/repositories/entities, groups them into
    per-controller business chunks via their actual dependency graph, and
    scores each chunk. No re-cloning, no GitHub API calls, no mock data.
    """
    try:
        result = await run_in_threadpool(_microservice_use_case.execute, job_id)
    except RepositoryBrowseError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content={"jobId": job_id, "status": exc.status, "message": exc.message},
        )

    return JSONResponse(status_code=200, content=result)
