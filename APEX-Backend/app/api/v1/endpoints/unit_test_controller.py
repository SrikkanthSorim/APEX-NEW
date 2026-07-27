"""Unit Test analysis/generation/execution/coverage endpoints (Result page's
Unit Test Report section). Thin controllers: validate ownership, delegate to
``UnitTestPipeline``, translate domain exceptions to the response contract --
no business logic lives here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_job_ownership
from app.application.pipelines.unit_test_pipeline import UnitTestPipeline
from app.application.services.unit_test_report_service import build_report_overlay
from app.core.exceptions import UnitTestError
from app.infrastructure.persistence.database import get_db
from app.infrastructure.persistence.models import User

router = APIRouter(tags=["unit-tests"])

_pipeline = UnitTestPipeline()


def _error_response(exc: UnitTestError, job_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content={"jobId": job_id, "status": exc.status, "message": exc.message},
    )


@router.post("/migration/{job_id}/unit-tests/analyze", summary="Detect production/existing test files.")
async def analyze_unit_tests(
    job_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> JSONResponse:
    verify_job_ownership(db, job_id, current_user)
    try:
        result = await run_in_threadpool(_pipeline.analyze, job_id)
    except UnitTestError as exc:
        return _error_response(exc, job_id)
    return JSONResponse(status_code=200, content=result)


@router.post("/migration/{job_id}/unit-tests/generate", summary="Generate missing unit tests only.")
async def generate_unit_tests(
    job_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> JSONResponse:
    verify_job_ownership(db, job_id, current_user)
    try:
        result = await run_in_threadpool(_pipeline.generate, job_id)
    except UnitTestError as exc:
        return _error_response(exc, job_id)
    return JSONResponse(status_code=200, content=result)


@router.post("/migration/{job_id}/unit-tests/run", summary="Compile, execute, and generate coverage.")
async def run_unit_tests(
    job_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> JSONResponse:
    verify_job_ownership(db, job_id, current_user)
    try:
        result = await run_in_threadpool(_pipeline.run, job_id)
    except UnitTestError as exc:
        return _error_response(exc, job_id)
    return JSONResponse(status_code=200, content=result)


@router.post(
    "/migration/{job_id}/unit-tests/rerun",
    summary="Re-execute existing + already-generated tests (never duplicates files).",
)
async def rerun_unit_tests(
    job_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> JSONResponse:
    """Returns the flat `{tests_run, tests_passed, ...}` overlay shape the
    Result page merges directly into its in-memory `MigrationResult` (see
    ResultReportView.tsx's `handleRerunTests`), not the raw persisted report.
    """
    verify_job_ownership(db, job_id, current_user)
    try:
        result = await run_in_threadpool(_pipeline.rerun, job_id)
    except UnitTestError as exc:
        return _error_response(exc, job_id)
    overlay = build_report_overlay(result)
    return JSONResponse(status_code=200, content={"job_id": job_id, **overlay})


@router.get("/migration/{job_id}/unit-tests/status", summary="Lightweight unit-test status (polled).")
async def unit_test_status(
    job_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> JSONResponse:
    verify_job_ownership(db, job_id, current_user)
    try:
        result = await run_in_threadpool(_pipeline.get_status, job_id)
    except UnitTestError as exc:
        return _error_response(exc, job_id)
    return JSONResponse(status_code=200, content=result)


@router.get("/migration/{job_id}/unit-tests/report", summary="Latest persisted unit test report.")
async def unit_test_report(
    job_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> JSONResponse:
    verify_job_ownership(db, job_id, current_user)
    try:
        result = await run_in_threadpool(_pipeline.get_report, job_id)
    except UnitTestError as exc:
        return _error_response(exc, job_id)
    return JSONResponse(status_code=200, content=result)


@router.get("/migration/{job_id}/unit-tests/report/download", summary="Downloadable HTML unit test report.")
async def download_unit_test_report(
    job_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> Response:
    verify_job_ownership(db, job_id, current_user)
    try:
        html_content = await run_in_threadpool(_pipeline.render_html_report, job_id)
    except UnitTestError as exc:
        return _error_response(exc, job_id)
    return Response(
        content=html_content,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="unit-test-report-{job_id}.html"'},
    )


@router.get("/migration/{job_id}/unit-tests/generated-files", summary="List of generated test files.")
async def unit_test_generated_files(
    job_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> JSONResponse:
    verify_job_ownership(db, job_id, current_user)
    try:
        result = await run_in_threadpool(_pipeline.get_generated_files, job_id)
    except UnitTestError as exc:
        return _error_response(exc, job_id)
    return JSONResponse(status_code=200, content=result)
