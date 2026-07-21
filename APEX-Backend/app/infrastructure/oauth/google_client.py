"""Thin async client for Google's OAuth 2.0 / OpenID Connect login flow.

Only talks HTTP to Google — no business decisions (find-or-create-user
logic lives in `app.application.services.auth_service.AuthService`). Mirrors
the style of `app.infrastructure.github.github_client.GithubClient`.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.exceptions import OAuthProviderError

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
# Identity-only scopes — no Drive/Calendar/etc access is ever requested.
SCOPES = "openid email profile"
REQUEST_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class GoogleUserProfile:
    """Normalized identity returned by Google — never the raw token payload."""

    provider_user_id: str
    email: str | None
    email_verified: bool
    full_name: str | None
    profile_image: str | None


def build_authorization_url(*, state: str, code_challenge: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


async def exchange_code_for_profile(*, code: str, code_verifier: str) -> GoogleUserProfile:
    """Exchange the authorization code for tokens, then fetch the user's profile.

    Raises `OAuthProviderError` for any transport failure or an unexpected
    response shape — callers never see a raw Google error body, and the
    access token obtained here is used once, in-memory, and discarded (never
    logged, never persisted).
    """
    token_payload = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            token_response = await client.post(TOKEN_ENDPOINT, data=token_payload)
            if token_response.status_code != 200:
                raise OAuthProviderError()
            token_data = token_response.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise OAuthProviderError()

            profile_response = await client.get(
                USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"}
            )
            if profile_response.status_code != 200:
                raise OAuthProviderError()
            profile_data = profile_response.json()
    except httpx.HTTPError as exc:  # transport / timeout / DNS
        raise OAuthProviderError() from exc
    except ValueError as exc:  # malformed JSON body
        raise OAuthProviderError() from exc

    provider_user_id = profile_data.get("sub")
    if not provider_user_id:
        raise OAuthProviderError()

    return GoogleUserProfile(
        provider_user_id=str(provider_user_id),
        email=profile_data.get("email"),
        email_verified=bool(profile_data.get("email_verified", False)),
        full_name=profile_data.get("name"),
        profile_image=profile_data.get("picture"),
    )
