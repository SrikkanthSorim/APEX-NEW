"""GitHub repo-visibility utility endpoint (unversioned — mounted at ``/api``).

The Connect step's frontend does an early PUBLIC/PRIVATE check against this
endpoint before submitting ``POST /api/v1/connect``. It reuses the same
:class:`RepoAccessChecker` / URL parser as the Connect flow, but never raises
on an ambiguous or missing token — it reports ``requires_token`` instead so
the UI can prompt for one rather than surfacing a hard error.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.application.use_cases.connect_repository import parse_github_url
from app.application.use_cases.generate_technical_document import GenerateTechnicalDocumentUseCase
from app.core.exceptions import (
    CloneFailedError,
    GithubServiceError,
    InvalidRepositoryUrlError,
    RepositoryAccessDeniedError,
    RepositoryNotFoundError,
)
from app.infrastructure.github.repo_access_checker import RepoAccessChecker
from app.schemas.document_schema import TechnicalDocumentRequest, TechnicalDocumentResponse
from app.schemas.github_schema import RepoVisibilityResponse

router = APIRouter(tags=["github"])

_access_checker = RepoAccessChecker()
_document_use_case = GenerateTechnicalDocumentUseCase()


@router.get(
    "/github/repo-visibility",
    response_model=RepoVisibilityResponse,
    summary="Best-effort PUBLIC/PRIVATE check for a GitHub repository URL.",
)
async def repo_visibility(
    repo_url: str = Query(..., description="GitHub repository URL to check."),
    token: str = Query("", description="Optional GitHub token."),
) -> JSONResponse:
    normalized_token = token.strip() or None

    try:
        parsed = parse_github_url(repo_url)
    except InvalidRepositoryUrlError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "owner": "",
                "repo": "",
                "visibility": "unknown",
                "requires_token": False,
                "message": exc.message,
            },
        )

    try:
        access = await _access_checker.check(parsed.owner, parsed.repo, token=normalized_token)
        return JSONResponse(
            status_code=200,
            content={
                "owner": access.owner,
                "repo": access.repo_name,
                "visibility": access.visibility.lower(),
                "requires_token": False,
                "message": "Repository access verified.",
            },
        )
    except RepositoryAccessDeniedError as exc:
        # Private (or ambiguous 404-without-token) — not an error state, the
        # frontend uses requires_token to prompt for a PAT.
        return JSONResponse(
            status_code=200,
            content={
                "owner": parsed.owner,
                "repo": parsed.repo,
                "visibility": "private_or_inaccessible",
                "requires_token": True,
                "message": exc.message,
            },
        )
    except RepositoryNotFoundError as exc:
        requires_token = normalized_token is None
        return JSONResponse(
            status_code=200,
            content={
                "owner": parsed.owner,
                "repo": parsed.repo,
                "visibility": "private_or_inaccessible" if requires_token else "unknown",
                "requires_token": requires_token,
                "message": exc.message,
            },
        )
    except GithubServiceError as exc:
        return JSONResponse(
            status_code=502,
            content={
                "owner": parsed.owner,
                "repo": parsed.repo,
                "visibility": "unknown",
                "requires_token": False,
                "message": exc.message,
            },
        )


@router.post(
    "/github/generate-brd-document",
    response_model=TechnicalDocumentResponse,
    summary="Generate a repository-grounded technical specification document.",
)
async def generate_brd_document(payload: TechnicalDocumentRequest) -> JSONResponse:
    """Generate PDF-ready HTML using real repository analysis.

    The legacy route name says BRD, but the current UI uses this action for the
    Technical Specification Document.
    """
    try:
        result = await run_in_threadpool(_document_use_case.execute, payload)
    except InvalidRepositoryUrlError as exc:
        return JSONResponse(status_code=400, content={"detail": exc.message})
    except RepositoryAccessDeniedError as exc:
        return JSONResponse(status_code=403, content={"detail": exc.message})
    except RepositoryNotFoundError as exc:
        return JSONResponse(status_code=404, content={"detail": exc.message})
    except CloneFailedError as exc:
        return JSONResponse(status_code=502, content={"detail": exc.message})
    except GithubServiceError as exc:
        return JSONResponse(status_code=502, content={"detail": exc.message})
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc) or "Failed to generate technical document."},
        )

    return JSONResponse(status_code=200, content=result)
