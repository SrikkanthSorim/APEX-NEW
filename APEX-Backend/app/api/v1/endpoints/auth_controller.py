"""Authentication endpoints: signup, login, me, refresh, logout.

Mounted at ``/api/auth/*`` — unversioned, like the other utility routers
(github, local-project, ...), see ``app/api/utility_router.py``. Thin
controller: request validation lives in ``app/schemas/auth_schema.py``,
business logic lives in ``app/application/services/auth_service.py``. This
file's only job is HTTP: status codes, and setting/clearing cookies.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.application.services.auth_service import AuthService
from app.core.config import settings
from app.core.exceptions import AuthError
from app.infrastructure.persistence.database import get_db
from app.infrastructure.persistence.models import User
from app.schemas.auth_schema import (
    AuthResponse,
    LoginRequest,
    MessageResponse,
    SignupRequest,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"


def _set_auth_cookies(response: JSONResponse, access_token: str, refresh_token: str) -> None:
    """Set both JWTs as HttpOnly cookies.

    HttpOnly means JavaScript (`document.cookie`) cannot read them, so a
    frontend XSS bug can't steal the tokens — they only ever travel between
    the browser's cookie jar and this server. Nothing is ever written to
    localStorage/sessionStorage.

    `secure=settings.is_production`: cookies require HTTPS in production,
    but not in local development over plain http://localhost (a browser
    will silently drop a `Secure` cookie sent over http://).
    """
    common_cookie_options = {
        "httponly": True,
        "secure": settings.is_production,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        **common_cookie_options,
    )
    response.set_cookie(
        REFRESH_TOKEN_COOKIE,
        refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        **common_cookie_options,
    )


def _clear_auth_cookies(response: JSONResponse) -> None:
    """Delete both cookies. Must use the SAME path/samesite used when they
    were set, or the browser treats it as a different cookie and won't
    actually remove the original one."""
    for cookie_name in (ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE):
        response.delete_cookie(cookie_name, path="/", samesite="lax")


def _auth_error_response(exc: AuthError) -> JSONResponse:
    # Safe logging: the error's stable `status` code and nothing else — never
    # the submitted password, a token value, or a stack trace.
    logger.info("Auth request rejected (%s).", exc.status)
    return JSONResponse(status_code=exc.http_status, content={"detail": exc.message})


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=201,
    summary="Create a new account (email + password).",
)
async def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> JSONResponse:
    """Creates the user and returns it. Does NOT log the user in — no cookies
    are set here, matching the frontend's "redirect to Sign In after signup"
    flow. No token or session is fabricated for an unverified new account.
    """
    service = AuthService(db)
    try:
        user = service.register(
            full_name=payload.full_name, email=payload.email, password=payload.password
        )
    except AuthError as exc:
        return _auth_error_response(exc)

    logger.info("New user registered (user_id=%s).", user.id)
    body = UserResponse.model_validate(user).model_dump(by_alias=True, mode="json")
    return JSONResponse(status_code=201, content=body)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Sign in with email and password.",
)
async def login(payload: LoginRequest, db: Session = Depends(get_db)) -> JSONResponse:
    service = AuthService(db)
    try:
        user = service.authenticate(email=payload.email, password=payload.password)
        service.record_login(user)
        access_token, refresh_token = service.issue_tokens(user)
    except AuthError as exc:
        return _auth_error_response(exc)

    logger.info("User logged in (user_id=%s).", user.id)
    body = AuthResponse(user=UserResponse.model_validate(user), message="Login successful.")
    response = JSONResponse(status_code=200, content=body.model_dump(by_alias=True, mode="json"))
    _set_auth_cookies(response, access_token, refresh_token)
    return response


@router.get(
    "/me",
    response_model=UserResponse,
    summary="The currently authenticated user.",
)
async def get_current_user_info(current_user: User = Depends(get_current_user)) -> JSONResponse:
    # `get_current_user` (see app/api/deps.py) already raised HTTP 401 for
    # every invalid case — reaching this line means the caller is logged in.
    body = UserResponse.model_validate(current_user).model_dump(by_alias=True, mode="json")
    return JSONResponse(status_code=200, content=body)


@router.post(
    "/refresh",
    response_model=MessageResponse,
    summary="Rotate the access/refresh token pair.",
)
async def refresh(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    raw_refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if not raw_refresh_token:
        return JSONResponse(status_code=401, content={"detail": "Refresh token is missing."})

    service = AuthService(db)
    try:
        _user, access_token, new_refresh_token = service.rotate_refresh_token(raw_refresh_token)
    except AuthError as exc:
        return _auth_error_response(exc)

    response = JSONResponse(status_code=200, content={"message": "Token refreshed."})
    _set_auth_cookies(response, access_token, new_refresh_token)
    return response


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Sign out and revoke the refresh token.",
)
async def logout(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    # No get_current_user dependency here on purpose: logout must succeed
    # even when the access token is already expired/missing — only the
    # refresh token cookie matters for revocation.
    raw_refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    AuthService(db).logout(raw_refresh_token)

    response = JSONResponse(status_code=200, content={"message": "Logged out."})
    _clear_auth_cookies(response)
    return response
