"""Project documentation endpoints backing the header "Docs" drawer."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.application.use_cases.generate_project_documentation import GenerateProjectDocumentationUseCase
from app.core.exceptions import CloneFailedError, MigrationJobNotFoundError

router = APIRouter(tags=["docs"])
_use_case = GenerateProjectDocumentationUseCase()


def _not_found_response() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "detail": {
                "code": "JOB_NOT_FOUND",
                "message": "No migration job found for this id.",
            }
        },
    )


@router.get("/docs/{job_id}", summary="Structured project documentation for the Docs drawer.")
async def get_docs(job_id: str) -> JSONResponse:
    try:
        result = await run_in_threadpool(_use_case.get_structured, job_id)
    except MigrationJobNotFoundError:
        return _not_found_response()
    return JSONResponse(status_code=200, content=result.model_dump())


@router.get("/docs/{job_id}/html", summary="Full downloadable project documentation HTML.")
async def get_docs_html(job_id: str) -> JSONResponse:
    try:
        result = await run_in_threadpool(_use_case.get_html, job_id)
    except MigrationJobNotFoundError:
        return _not_found_response()
    except CloneFailedError as exc:
        return JSONResponse(status_code=502, content={"detail": exc.message})
    return JSONResponse(status_code=200, content=result)
