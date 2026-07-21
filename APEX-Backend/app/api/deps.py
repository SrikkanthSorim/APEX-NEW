"""Shared FastAPI dependencies for the API layer."""

from __future__ import annotations

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
