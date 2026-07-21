"""Password hashing and JWT helpers.

For a Java/Spring developer: this module is the equivalent of a small
`PasswordEncoder` + `JwtService` pair — `pwdlib` (Argon2) plays the role of
`BCryptPasswordEncoder`, and `PyJWT` plays the role of `jjwt`/`java-jwt`.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

logger = logging.getLogger(__name__)

# PasswordHash.recommended() currently resolves to Argon2id with sane default
# parameters (memory/time cost). Like a Spring `PasswordEncoder`, this single
# object knows how to both hash and verify passwords.
_password_hasher = PasswordHash.recommended()

TokenType = Literal["access", "refresh"]


class InvalidTokenError(Exception):
    """Raised for any JWT that is missing, malformed, expired, or the wrong type."""


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with Argon2. The plaintext is never stored."""
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored Argon2 hash.

    Returns False instead of raising if the stored hash is malformed/corrupt,
    so a bad row can never crash the login endpoint with a 500.
    """
    try:
        return _password_hasher.verify(plain_password, password_hash)
    except Exception:
        logger.warning("Password verification failed against a malformed stored hash.")
        return False


# --------------------------------------------------------------------------- #
# JWT access/refresh tokens
# --------------------------------------------------------------------------- #


def _create_token(user_id: int, token_type: TokenType, expires_delta: timedelta) -> str:
    """Build and sign a JWT.

    `sub` (subject) is the standard JWT claim for "who this token is about" —
    here, the user's database id. No email/name/role is placed in the
    payload: the token is just a signed pointer to a user row, so nothing
    sensitive leaks if a token is ever intercepted or logged by mistake.
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        # "jti" (JWT ID): a random unique id per token. Without this, two
        # refresh tokens issued in the same second for the same user would
        # be byte-for-byte identical, which would break refresh-token
        # rotation's "reject the old token" check.
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int) -> str:
    """Short-lived token proving the caller is logged in (sent on every request)."""
    return _create_token(user_id, "access", timedelta(minutes=settings.access_token_expire_minutes))


def create_refresh_token(user_id: int) -> str:
    """Long-lived token used only to obtain a new access token (see /api/auth/refresh)."""
    return _create_token(user_id, "refresh", timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, expected_type: TokenType) -> int:
    """Decode and validate a JWT, returning the user id encoded in ``sub``.

    Raises InvalidTokenError for anything that isn't a currently-valid token
    of the expected type: expired, malformed, wrong signature, or a token of
    the *other* type (e.g. a refresh token presented where an access token
    is required, or vice versa).
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        # Base class for every other PyJWT failure: bad signature, malformed
        # payload, wrong algorithm, etc. Deliberately not more specific in
        # the message returned to callers — internals stay internal.
        raise InvalidTokenError("Token is invalid.") from exc

    if payload.get("type") != expected_type:
        raise InvalidTokenError(f"Expected a '{expected_type}' token.")

    subject = payload.get("sub")
    if subject is None:
        raise InvalidTokenError("Token is missing its subject.")

    try:
        return int(subject)
    except (TypeError, ValueError) as exc:
        raise InvalidTokenError("Token subject is not a valid user id.") from exc


# --------------------------------------------------------------------------- #
# Refresh-token hashing (for storage/lookup — NOT the same as password hashing)
# --------------------------------------------------------------------------- #


def hash_refresh_token(raw_token: str) -> str:
    """Deterministically hash a refresh token for storage and lookup.

    Refresh tokens (unlike passwords) are already long, random, high-entropy
    JWT strings, so a fast *deterministic* hash (SHA-256) is the right tool
    here — it lets the database look a token up with
    ``WHERE token_hash = ?``. Argon2 is deliberately NOT used for this: it
    salts differently on every call, so the same input would never hash to
    the same value twice, making a lookup-by-hash impossible.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# OAuth (Google / GitHub social login): state (CSRF) tokens + PKCE
# --------------------------------------------------------------------------- #

_OAUTH_STATE_TOKEN_TYPE = "oauth_state"


def create_oauth_state_token(provider: str) -> str:
    """Build a short-lived, self-verifying `state` value for an OAuth login.

    Sent as the `state` query parameter to Google/GitHub and echoed straight
    back to our callback — signing it here (instead of using a server-side
    session store) is what lets the callback later prove the request came
    from an authorization flow *we* started, for *this* provider, within the
    last `settings.oauth_state_expire_seconds`, without persisting anything.
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "type": _OAUTH_STATE_TOKEN_TYPE,
        "provider": provider,
        "nonce": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + timedelta(seconds=settings.oauth_state_expire_seconds),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_oauth_state_token(token: str, expected_provider: str) -> None:
    """Validate an OAuth `state` value. Raises InvalidTokenError if it is
    missing, unsigned, expired, or was issued for a different provider."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("OAuth state has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("OAuth state is invalid.") from exc

    if payload.get("type") != _OAUTH_STATE_TOKEN_TYPE or payload.get("provider") != expected_provider:
        raise InvalidTokenError("OAuth state is invalid.")


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE (RFC 7636) `(code_verifier, code_challenge)` pair.

    `code_challenge` (S256 of `code_verifier`) is sent up front in the
    authorization request; `code_verifier` itself is kept server-side (a
    short-lived HttpOnly cookie — see the Google login/callback routes) and
    only sent later, directly to the token endpoint, so a stolen
    authorization code alone can't be redeemed by anyone else.
    """
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge
