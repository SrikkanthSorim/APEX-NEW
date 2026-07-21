"""Thin async client for GitHub's OAuth "web application flow" login.

Only talks HTTP to GitHub — no business decisions. Deliberately separate
from `app.infrastructure.github.github_client.GithubClient`, which is used
for the unrelated "check/create a repository" feature (Connect stage) and
only ever uses a long-lived personal access token (GITHUB_TOKEN /
GITHUB_TARGET_TOKEN) — never this OAuth login flow's client id/secret, and
never the short-lived user access token obtained here.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.exceptions import OAuthProviderError

AUTHORIZATION_ENDPOINT = "https://github.com/login/oauth/authorize"
TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"
USER_ENDPOINT = "https://api.github.com/user"
EMAILS_ENDPOINT = "https://api.github.com/user/emails"
# Identity-only scopes. Deliberately NOT "repo" (or any repository scope) —
# logging in with GitHub must never grant private-repository access; that
# stays the Connect stage's separate PAT-based flow.
SCOPES = "read:user user:email"
REQUEST_TIMEOUT_SECONDS = 15.0
_API_VERSION_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "java-migration-platform",
}


@dataclass(frozen=True)
class GithubUserProfile:
    """Normalized identity returned by GitHub — never the raw token payload."""

    provider_user_id: str
    email: str | None
    email_verified: bool
    full_name: str | None
    profile_image: str | None


def build_authorization_url(*, state: str) -> str:
    # GitHub's OAuth App web flow (unlike Google's) has no PKCE support — the
    # signed `state` value is this flow's only CSRF protection.
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_redirect_uri,
        "scope": SCOPES,
        "state": state,
        "allow_signup": "true",
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


async def exchange_code_for_profile(*, code: str) -> GithubUserProfile:
    """Exchange the authorization code for an access token, then fetch the
    user's profile (and, if needed, their verified primary email).

    Raises `OAuthProviderError` for any transport failure or an unexpected
    response shape. The access token obtained here is used once, in-memory,
    and discarded (never logged, never persisted).
    """
    token_payload = {
        "client_id": settings.github_client_id,
        "client_secret": settings.github_client_secret,
        "redirect_uri": settings.github_redirect_uri,
        "code": code,
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            token_response = await client.post(
                TOKEN_ENDPOINT,
                data=token_payload,
                headers={"Accept": "application/json"},
            )
            if token_response.status_code != 200:
                raise OAuthProviderError()
            token_data = token_response.json()
            access_token = token_data.get("access_token")
            if not access_token or token_data.get("error"):
                raise OAuthProviderError()

            auth_headers = {**_API_VERSION_HEADERS, "Authorization": f"Bearer {access_token}"}
            user_response = await client.get(USER_ENDPOINT, headers=auth_headers)
            if user_response.status_code != 200:
                raise OAuthProviderError()
            user_data = user_response.json()

            email = user_data.get("email")
            email_verified = False
            if email:
                # The primary email on GET /user is only ever populated when
                # it is public — and GitHub only ever reports a verified
                # address here, so a non-null value is already verified.
                email_verified = True
            else:
                # Private/hidden primary email — the dedicated emails API is
                # the only way to retrieve it (per product spec).
                emails_response = await client.get(EMAILS_ENDPOINT, headers=auth_headers)
                if emails_response.status_code == 200:
                    for entry in emails_response.json():
                        if isinstance(entry, dict) and entry.get("primary") and entry.get("verified"):
                            email = entry.get("email")
                            email_verified = True
                            break
    except httpx.HTTPError as exc:  # transport / timeout / DNS
        raise OAuthProviderError() from exc
    except ValueError as exc:  # malformed JSON body
        raise OAuthProviderError() from exc

    provider_user_id = user_data.get("id")
    if provider_user_id is None:
        raise OAuthProviderError()

    return GithubUserProfile(
        provider_user_id=str(provider_user_id),
        email=email,
        email_verified=email_verified,
        full_name=user_data.get("name") or user_data.get("login"),
        profile_image=user_data.get("avatar_url"),
    )
