"""Authentication business logic: registration, login, tokens, logout.

Keeps HTTP concerns (status codes, cookies, JSON shapes) out of this layer —
`app/api/v1/endpoints/auth_controller.py` is the only place that touches
`Request`/`Response`/cookies. This mirrors a Spring `@Service` sitting
between a `@RestController` and a `@Repository`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.core.exceptions import (
    AccountDisabledError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    NotAuthenticatedError,
)
from app.infrastructure.persistence import user_repository
from app.infrastructure.persistence.models import User


class AuthService:
    """Built once per request with that request's database session."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # --- Registration ----------------------------------------------------------

    def register(self, *, full_name: str, email: str, password: str) -> User:
        """Create a new local (email/password) user.

        `email` must already be normalized (trimmed + lowercased) — the
        `SignupRequest` schema does this before the service ever sees it.
        """
        if user_repository.get_user_by_email(self._db, email) is not None:
            raise EmailAlreadyRegisteredError()

        password_hash = security.hash_password(password)
        try:
            return user_repository.create_user(
                self._db, full_name=full_name, email=email, password_hash=password_hash
            )
        except IntegrityError as exc:
            # Two signups for the same email arrived at (almost) the same
            # time and both passed the get_user_by_email check above — the
            # database's unique constraint is the real safety net here.
            raise EmailAlreadyRegisteredError() from exc

    # --- Login -------------------------------------------------------------

    def authenticate(self, *, email: str, password: str) -> User:
        """Verify credentials and return the matching active user.

        Security notes:
        - Unknown email and wrong password raise the SAME
          `InvalidCredentialsError` — a caller can never tell which one
          happened, so this endpoint can't be used to discover which emails
          are registered.
        - The password is checked BEFORE the `is_active` check. If we
          checked `is_active` first, an attacker could probe arbitrary
          emails with a random password and learn "this account exists and
          is disabled" without ever knowing the real password — that would
          itself be an email-enumeration leak. Checking the password first
          means only someone who already knows the correct password learns
          that the account is disabled.
        """
        user = user_repository.get_user_by_email(self._db, email)
        if user is None or user.password_hash is None:
            raise InvalidCredentialsError()
        if not security.verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise AccountDisabledError()

        return user

    def record_login(self, user: User) -> None:
        user_repository.update_last_login(self._db, user)

    # --- Tokens --------------------------------------------------------------

    def issue_tokens(self, user: User) -> tuple[str, str]:
        """Create a fresh (access_token, refresh_token) pair and persist the
        refresh token's hash so it can be validated/rotated/revoked later."""
        access_token = security.create_access_token(user.id)
        refresh_token = security.create_refresh_token(user.id)
        self._store_refresh_token(user.id, refresh_token)
        return access_token, refresh_token

    def _store_refresh_token(self, user_id: int, raw_refresh_token: str) -> None:
        token_hash = security.hash_refresh_token(raw_refresh_token)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        user_repository.create_refresh_token_record(
            self._db, user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )

    def rotate_refresh_token(self, raw_refresh_token: str) -> tuple[User, str, str]:
        """Validate + rotate a refresh token.

        On success the OLD token is revoked and a brand new
        (access_token, refresh_token) pair is issued and stored — this is
        "refresh-token rotation". Rejects a token that is expired,
        malformed/wrong signature, already revoked, or already rotated
        (reused).
        """
        try:
            token_user_id = security.decode_token(raw_refresh_token, expected_type="refresh")
        except security.InvalidTokenError as exc:
            raise InvalidRefreshTokenError(str(exc)) from exc

        token_hash = security.hash_refresh_token(raw_refresh_token)
        record = user_repository.get_refresh_token_by_hash(self._db, token_hash)
        if record is None:
            raise InvalidRefreshTokenError()
        if record.revoked_at is not None:
            # Either a normal logout revoked it, or (more interestingly) this
            # exact refresh token was already used once to rotate — reusing
            # a rotated-away token is treated as invalid, not silently
            # accepted, which is the whole point of rotation.
            raise InvalidRefreshTokenError("Refresh token has already been used.")
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            # PostgreSQL's TIMESTAMPTZ always round-trips as timezone-aware
            # via psycopg, so this branch shouldn't fire in production — it's
            # a defensive normalization for any DB backend/driver that drops
            # tzinfo on read (e.g. SQLite, used by this project's tests).
            # Every expires_at is written in UTC (see _store_refresh_token),
            # so a naive value can be safely assumed to already be UTC.
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise InvalidRefreshTokenError("Refresh token has expired.")
        if record.user_id != token_user_id:
            raise InvalidRefreshTokenError()

        user = user_repository.get_user_by_id(self._db, token_user_id)
        if user is None or not user.is_active:
            raise InvalidRefreshTokenError()

        # Revoke the OLD token before issuing the new one. If the process
        # crashed between these two lines, the old token stays permanently
        # unusable (fails closed) rather than staying valid (fails open).
        user_repository.revoke_refresh_token(self._db, record)

        access_token = security.create_access_token(user.id)
        new_refresh_token = security.create_refresh_token(user.id)
        self._store_refresh_token(user.id, new_refresh_token)
        return user, access_token, new_refresh_token

    # --- Current user --------------------------------------------------------

    def get_user_from_access_token(self, raw_access_token: str | None) -> User:
        """Used by the `get_current_user` FastAPI dependency (see `app/api/deps.py`)."""
        if not raw_access_token:
            raise NotAuthenticatedError("Missing access token.")
        try:
            user_id = security.decode_token(raw_access_token, expected_type="access")
        except security.InvalidTokenError as exc:
            raise NotAuthenticatedError(str(exc)) from exc

        user = user_repository.get_user_by_id(self._db, user_id)
        if user is None or not user.is_active:
            raise NotAuthenticatedError()
        return user

    # --- Logout ----------------------------------------------------------------

    def logout(self, raw_refresh_token: str | None) -> None:
        """Revoke the refresh token if present and still valid.

        Deliberately never raises: per spec, logout must stay safe and
        successful even when the cookie is already missing or the refresh
        token is already invalid/revoked.
        """
        if not raw_refresh_token:
            return
        token_hash = security.hash_refresh_token(raw_refresh_token)
        record = user_repository.get_refresh_token_by_hash(self._db, token_hash)
        if record is not None and record.revoked_at is None:
            user_repository.revoke_refresh_token(self._db, record)
