"""Local-project capabilities endpoint (unversioned — mounted at ``/api``).

The Connect step's "Upload Local Project" panel probes this on load to decide
what to tell the user. The upload/analyze pipeline for local projects has not
been built on this backend yet, so this honestly reports the feature as
disabled instead of 404-ing (which previously broke the capabilities probe).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.application.use_cases.generate_technical_document import GenerateTechnicalDocumentUseCase
from app.schemas.document_schema import TechnicalDocumentRequest, TechnicalDocumentResponse
from app.schemas.local_project_schema import LocalProjectCapabilitiesResponse

router = APIRouter(tags=["local-project"])
_document_use_case = GenerateTechnicalDocumentUseCase()


@router.get(
    "/local-project/capabilities",
    response_model=LocalProjectCapabilitiesResponse,
    summary="Report whether local-project upload/analysis is available.",
)
async def local_project_capabilities() -> LocalProjectCapabilitiesResponse:
    return LocalProjectCapabilitiesResponse(
        enabled=False,
        hosted_mode=True,
        allow_any_path=False,
        allowed_roots=[],
        supports_upload=False,
        message="Local project upload isn't available yet — connect a GitHub repository instead.",
    )


@router.post(
    "/local-project/generate-brd-document",
    response_model=TechnicalDocumentResponse,
    summary="Generate a technical specification document from uploaded-project analysis.",
)
async def generate_local_project_brd_document(payload: TechnicalDocumentRequest) -> JSONResponse:
    try:
        result = await run_in_threadpool(_document_use_case.execute, payload)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc) or "Failed to generate technical document."},
        )

    return JSONResponse(status_code=200, content=result)
