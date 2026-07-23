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
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.application.services.auth_service import AuthService
from app.core import security
from app.core.config import settings
from app.core.exceptions import AuthError
from app.infrastructure.oauth import github_client, google_client
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

# HttpOnly cookie holding the PKCE code_verifier between "/google/login" and
# "/google/callback" (see app.core.security.generate_pkce_pair). GitHub's
# OAuth App flow has no PKCE support, so it has no equivalent cookie.
OAUTH_PKCE_COOKIE = "oauth_pkce_verifier"
OAUTH_PKCE_COOKIE_PATH = "/api/auth/google"

# Maps an internal AuthError.status to the public, stable code appended as
# `?oauth_error=<code>` on the sign-in redirect — never the exception's own
# (safe, but internal-vocabulary) message.
_OAUTH_ERROR_CODES: dict[str, str] = {
    "OAUTH_NOT_CONFIGURED": "provider_not_configured",
    "OAUTH_CANCELLED": "access_denied",
    "OAUTH_INVALID_STATE": "invalid_state",
    "OAUTH_PROVIDER_ERROR": "provider_error",
    "OAUTH_EMAIL_MISSING": "missing_email",
    "OAUTH_ACCOUNT_CONFLICT": "account_conflict",
    "ACCOUNT_DISABLED": "account_disabled",
}


def _set_auth_cookies(response: JSONResponse, access_token: str, refresh_token: str) -> None:
    """Set both JWTs as HttpOnly cookies.

    HttpOnly means JavaScript (`document.cookie`) cannot read them, so a
    frontend XSS bug can't steal the tokens — they only ever travel between
    the browser's cookie jar and this server. Nothing is ever written to
    localStorage/sessionStorage.

    `secure=settings.is_production`: cookies require HTTPS in production,
    but not in local development over plain http://localhost (a browser
    will silently drop a `Secure` cookie sent over http://).

    `samesite=settings.cookie_samesite`: "none" in production, where the
    frontend is served from a different host than this API and every call is
    therefore cross-site; "lax" locally. See the property for why the two
    environments cannot share one value.
    """
    common_cookie_options = {
        "httponly": True,
        "secure": settings.is_production,
        "samesite": settings.cookie_samesite,
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
    """Delete both cookies. Must use the SAME path/samesite/secure used when
    they were set, or the browser treats it as a different cookie and won't
    actually remove the original one.

    `secure` is not optional here despite this being a deletion: a browser
    rejects any `SameSite=None` cookie that is not also `Secure`, so omitting
    it in production would make the deletion itself be discarded and logout
    would silently leave the user signed in.
    """
    for cookie_name in (ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE):
        response.delete_cookie(
            cookie_name,
            path="/",
            samesite=settings.cookie_samesite,
            secure=settings.is_production,
            httponly=True,
        )


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
        access_token, refresh_token = service.create_login_session(user)
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


# --- OAuth (Google / GitHub social login) -----------------------------------
#
# Every route below is a browser REDIRECT, never a JSON response — the
# frontend never calls these via fetch(); a click on the Google/GitHub
# button navigates the whole page to "<login>", which redirects to the
# provider, which redirects back to "<callback>", which redirects to
# FRONTEND_URL (either "/connect" on success or "/signin?oauth_error=<code>"
# on failure). No provider secret, access token, or stack trace ever
# reaches the browser or the logs — see `_OAUTH_ERROR_CODES` above.


def _oauth_error_redirect(error_code: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"{settings.frontend_url}/signin?oauth_error={error_code}",
        status_code=302,
    )


def _oauth_success_redirect(access_token: str, refresh_token: str) -> RedirectResponse:
    response = RedirectResponse(url=f"{settings.frontend_url}/connect", status_code=302)
    _set_auth_cookies(response, access_token, refresh_token)
    return response


@router.get("/google/login", summary="Redirect the browser to Google's consent screen.")
async def google_login() -> RedirectResponse:
    if not settings.google_oauth_configured:
        return _oauth_error_redirect("provider_not_configured")

    state = security.create_oauth_state_token("google")
    code_verifier, code_challenge = security.generate_pkce_pair()
    authorization_url = google_client.build_authorization_url(state=state, code_challenge=code_challenge)

    response = RedirectResponse(url=authorization_url, status_code=302)
    response.set_cookie(
        OAUTH_PKCE_COOKIE,
        code_verifier,
        max_age=settings.oauth_state_expire_seconds,
        httponly=True,
        secure=settings.is_production,
        samesite=settings.cookie_samesite,
        path=OAUTH_PKCE_COOKIE_PATH,
    )
    return response


@router.get("/google/callback", summary="Google's OAuth redirect target.")
async def google_callback(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    if request.query_params.get("error"):
        logger.info("Google OAuth denied/cancelled by the user.")
        return _oauth_error_redirect("access_denied")

    state = request.query_params.get("state")
    code = request.query_params.get("code")
    code_verifier = request.cookies.get(OAUTH_PKCE_COOKIE)
    if not state or not code or not code_verifier:
        return _oauth_error_redirect("invalid_state")

    try:
        security.decode_oauth_state_token(state, expected_provider="google")
    except security.InvalidTokenError:
        return _oauth_error_redirect("invalid_state")

    try:
        profile = await google_client.exchange_code_for_profile(code=code, code_verifier=code_verifier)
        service = AuthService(db)
        user = service.authenticate_with_oauth(
            provider="google",
            provider_user_id=profile.provider_user_id,
            email=profile.email,
            email_verified=profile.email_verified,
            full_name=profile.full_name,
            profile_image=profile.profile_image,
        )
        access_token, refresh_token = service.create_login_session(user)
    except AuthError as exc:
        logger.info("Google OAuth login rejected (%s).", exc.status)
        return _oauth_error_redirect(_OAUTH_ERROR_CODES.get(exc.status, "server_error"))
    except Exception:
        logger.exception("Unexpected error completing Google OAuth login.")
        return _oauth_error_redirect("server_error")

    logger.info("User logged in via Google OAuth (user_id=%s).", user.id)
    response = _oauth_success_redirect(access_token, refresh_token)
    response.delete_cookie(
        OAUTH_PKCE_COOKIE,
        path=OAUTH_PKCE_COOKIE_PATH,
        samesite=settings.cookie_samesite,
        secure=settings.is_production,
        httponly=True,
    )
    return response


@router.get("/github/login", summary="Redirect the browser to GitHub's consent screen.")
async def github_login() -> RedirectResponse:
    if not settings.github_oauth_configured:
        return _oauth_error_redirect("provider_not_configured")

    state = security.create_oauth_state_token("github")
    authorization_url = github_client.build_authorization_url(state=state)
    return RedirectResponse(url=authorization_url, status_code=302)


@router.get("/github/callback", summary="GitHub's OAuth redirect target.")
async def github_callback(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    if request.query_params.get("error"):
        logger.info("GitHub OAuth denied/cancelled by the user.")
        return _oauth_error_redirect("access_denied")

    state = request.query_params.get("state")
    code = request.query_params.get("code")
    if not state or not code:
        return _oauth_error_redirect("invalid_state")

    try:
        security.decode_oauth_state_token(state, expected_provider="github")
    except security.InvalidTokenError:
        return _oauth_error_redirect("invalid_state")

    try:
        profile = await github_client.exchange_code_for_profile(code=code)
        service = AuthService(db)
        user = service.authenticate_with_oauth(
            provider="github",
            provider_user_id=profile.provider_user_id,
            email=profile.email,
            email_verified=profile.email_verified,
            full_name=profile.full_name,
            profile_image=profile.profile_image,
        )
        access_token, refresh_token = service.create_login_session(user)
    except AuthError as exc:
        logger.info("GitHub OAuth login rejected (%s).", exc.status)
        return _oauth_error_redirect(_OAUTH_ERROR_CODES.get(exc.status, "server_error"))
    except Exception:
        logger.exception("Unexpected error completing GitHub OAuth login.")
        return _oauth_error_redirect("server_error")

    logger.info("User logged in via GitHub OAuth (user_id=%s).", user.id)
    return _oauth_success_redirect(access_token, refresh_token)
