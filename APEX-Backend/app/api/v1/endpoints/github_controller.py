"""GitHub repo-visibility utility endpoint (unversioned — mounted at ``/api``).

The Connect step's frontend does an early PUBLIC/PRIVATE check against this
endpoint before submitting ``POST /api/v1/connect``. It reuses the same
:class:`RepoAccessChecker` / URL parser as the Connect flow, but never raises
on an ambiguous or missing token — it reports ``requires_token`` instead so
the UI can prompt for one rather than surfacing a hard error.
"""

from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.api.deps import github_token_from_header
from app.application.use_cases.analyze_repo_url import AnalyzeRepoUrlUseCase
from app.application.use_cases.connect_repository import parse_github_url
from app.application.use_cases.generate_technical_document import GenerateTechnicalDocumentUseCase
from app.core.exceptions import (
    CloneFailedError,
    GithubServiceError,
    InvalidRepositoryUrlError,
    RepositoryAccessDeniedError,
    RepositoryNotFoundError,
)
from app.infrastructure.github.github_client import GithubClient
from app.infrastructure.github.repo_access_checker import RepoAccessChecker
from app.schemas.document_schema import TechnicalDocumentRequest, TechnicalDocumentResponse
from app.schemas.github_schema import (
    FileContentResponse,
    RepoFilesResponse,
    RepoUrlAnalysisResponse,
    RepoVisibilityResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["github"])

_access_checker = RepoAccessChecker()
_document_use_case = GenerateTechnicalDocumentUseCase()
_github_client = GithubClient()
_analyze_use_case = AnalyzeRepoUrlUseCase()


@router.get(
    "/github/repo-visibility",
    response_model=RepoVisibilityResponse,
    summary="Best-effort PUBLIC/PRIVATE check for a GitHub repository URL.",
)
async def repo_visibility(
    repo_url: str = Query(..., description="GitHub repository URL to check."),
    token: str = Depends(github_token_from_header),
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
    except Exception:
        # Log the real cause server-side; never return raw exception text to the
        # client (it can leak implementation details).
        logger.exception("Unexpected error generating technical document.")
        return JSONResponse(
            status_code=500,
            content={"detail": "Failed to generate technical document."},
        )

    return JSONResponse(status_code=200, content=result)


def _contents_error_response(status_code: int) -> JSONResponse | None:
    """Map a GitHub contents-API status to a client response, or None on success."""
    if status_code == 200:
        return None
    if status_code == 404:
        return JSONResponse(status_code=404, content={"detail": "Path not found in repository."})
    if status_code in (401, 403):
        return JSONResponse(
            status_code=status_code,
            content={"detail": "Access denied. A valid GitHub token may be required."},
        )
    return JSONResponse(status_code=502, content={"detail": "Failed to read repository contents."})


@router.get(
    "/github/list-files",
    response_model=RepoFilesResponse,
    summary="List files/folders at a path in a GitHub repository (by URL).",
)
async def list_files(
    repo_url: str = Query(..., description="GitHub repository URL."),
    path: str = Query("", description="Folder path relative to the repository root."),
    token: str = Depends(github_token_from_header),
) -> JSONResponse:
    try:
        parsed = parse_github_url(repo_url)
    except InvalidRepositoryUrlError as exc:
        return JSONResponse(status_code=400, content={"detail": exc.message})

    result = await _github_client.get_contents(
        parsed.owner, parsed.repo, path, token=token.strip() or None
    )
    error = _contents_error_response(result.status_code)
    if error is not None:
        return error
    if result.data is None:
        return JSONResponse(status_code=502, content={"detail": "Failed to list repository files."})

    entries = result.data if isinstance(result.data, list) else [result.data]
    files = [
        {
            "name": entry.get("name", ""),
            "path": entry.get("path", ""),
            "type": "dir" if entry.get("type") == "dir" else "file",
            "size": int(entry.get("size") or 0),
            "url": entry.get("html_url") or "",
        }
        for entry in entries
        if isinstance(entry, dict)
    ]
    return JSONResponse(
        status_code=200,
        content={
            "repo_url": repo_url,
            "owner": parsed.owner,
            "repo": parsed.repo,
            "path": path,
            "files": files,
        },
    )


@router.get(
    "/github/file-content",
    response_model=FileContentResponse,
    summary="Read a text file's content from a GitHub repository (by URL).",
)
async def file_content(
    repo_url: str = Query(..., description="GitHub repository URL."),
    file_path: str = Query(..., description="File path relative to the repository root."),
    token: str = Depends(github_token_from_header),
) -> JSONResponse:
    try:
        parsed = parse_github_url(repo_url)
    except InvalidRepositoryUrlError as exc:
        return JSONResponse(status_code=400, content={"detail": exc.message})

    result = await _github_client.get_contents(
        parsed.owner, parsed.repo, file_path, token=token.strip() or None
    )
    error = _contents_error_response(result.status_code)
    if error is not None:
        return error
    if isinstance(result.data, list):
        return JSONResponse(status_code=400, content={"detail": "Path is a directory, not a file."})
    if not isinstance(result.data, dict) or result.data.get("type") != "file":
        return JSONResponse(status_code=400, content={"detail": "Requested path is not a readable file."})

    encoded = result.data.get("content")
    if result.data.get("encoding") != "base64" or not encoded:
        # GitHub returns empty content for files above ~1 MB via this endpoint.
        return JSONResponse(
            status_code=413,
            content={"detail": "File is too large or not previewable as text."},
        )
    try:
        text = base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return JSONResponse(status_code=415, content={"detail": "File is not a UTF-8 text file."})

    return JSONResponse(
        status_code=200,
        content={
            "repo_url": repo_url,
            "owner": parsed.owner,
            "repo": parsed.repo,
            "file_path": file_path,
            "content": text,
        },
    )


@router.get(
    "/github/analyze-url",
    response_model=RepoUrlAnalysisResponse,
    summary="Analyze a GitHub repository by URL (clone-and-analyze, no persisted job).",
)
async def analyze_url(
    repo_url: str = Query(..., description="GitHub repository URL to analyze."),
    force_refresh: bool = Query(False, description="Accepted for compatibility; no cache layer."),
    token: str = Depends(github_token_from_header),
) -> JSONResponse:
    try:
        result = await run_in_threadpool(
            _analyze_use_case.execute, repo_url, token.strip() or None
        )
    except InvalidRepositoryUrlError as exc:
        return JSONResponse(status_code=400, content={"detail": exc.message})
    except CloneFailedError as exc:
        return JSONResponse(status_code=502, content={"detail": exc.message})
    except GithubServiceError as exc:
        return JSONResponse(status_code=502, content={"detail": exc.message})
    except Exception:
        logger.exception("Unexpected error analyzing repository by URL.")
        return JSONResponse(status_code=500, content={"detail": "Failed to analyze repository."})

    return JSONResponse(status_code=200, content=result)
