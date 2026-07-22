"""Shared FastAPI dependencies for authenticated/protected endpoints.

`get_current_user` is used like `user: User = Depends(get_current_user)` in
any route that requires a logged-in user — similar to a Spring Security
`@AuthenticationPrincipal` argument resolver. `verify_job_ownership` is the
equivalent for "is this user allowed to see this specific migration job".
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.application.services.auth_service import AuthService
from app.core.exceptions import NotAuthenticatedError
from app.infrastructure.persistence.database import get_db
from app.infrastructure.persistence.migration_ownership_repository import get_job_owner_user_id
from app.infrastructure.persistence.models import User

ACCESS_TOKEN_COOKIE_NAME = "access_token"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve the logged-in user from the `access_token` HttpOnly cookie.

    Raises HTTP 401 for every failure case the spec calls out: missing
    cookie, malformed/invalid signature, expired token, wrong token type
    (e.g. a refresh token used here), or a token whose user no longer
    exists or has been deactivated. The frontend only ever sees a generic
    401 — which of these happened is not distinguishable from the response.
    """
    raw_token = request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
    try:
        return AuthService(db).get_user_from_access_token(raw_token)
    except NotAuthenticatedError as exc:
        raise HTTPException(status_code=401, detail=exc.message) from exc


def verify_job_ownership(db: Session, job_id: str, current_user: User) -> None:
    """Raise 403/404 unless `current_user` is the recorded owner of `job_id`.

    Ownership is recorded once, at job-creation time, in
    `POST /api/v1/connect` (see
    `app.infrastructure.persistence.migration_ownership_repository.record_job_owner`).
    A job with no ownership record at all (for example one created on disk
    before this feature existed) is treated as forbidden rather than
    silently allowed — the caller's identity is never inferred from
    anything the frontend sends, only from `get_current_user`.
    """
    owner_user_id = get_job_owner_user_id(db, job_id)
    if owner_user_id is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "JOB_NOT_FOUND", "message": "No migration job found for this id."},
        )
    if owner_user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "You do not have access to this migration job."},
        )

"""Shared FastAPI dependencies for the API layer."""

from fastapi import Header

_BEARER_PREFIX = "bearer "


def github_token_from_header(authorization: str | None = Header(default=None)) -> str:
    """Extract a GitHub PAT from the ``Authorization: Bearer <token>`` header.

    The token is passed as a header (never in the URL query string) so it never
    leaks through browser history, server logs, proxies, or referrers. Returns an
    empty string when the header is absent or malformed, preserving the previous
    "optional token" behavior for public repositories.
    """
    if not authorization:
        return ""
    value = authorization.strip()
    if value.lower().startswith(_BEARER_PREFIX):
        return value[len(_BEARER_PREFIX):].strip()
    return ""
