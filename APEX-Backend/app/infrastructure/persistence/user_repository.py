"""Database access for users and refresh tokens.

Repository functions take a SQLAlchemy `Session` and return ORM objects (or
`None`) — no HTTP concerns (status codes, JSON shapes) belong here. The
service layer (`app.application.services.auth_service`) turns these results
into API responses. This mirrors a Spring `@Repository`/JPA `Repository`
sitting below a `@Service`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models import RefreshToken, User

logger = logging.getLogger(__name__)


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> User | None:
    """`email` must already be normalized (trimmed + lowercased) by the caller."""
    statement = select(User).where(User.email == email)
    return db.execute(statement).scalar_one_or_none()


def create_user(db: Session, *, full_name: str, email: str, password_hash: str) -> User:
    """Insert a new local (email/password) user.

    Raises `sqlalchemy.exc.IntegrityError` (a subclass of `SQLAlchemyError`)
    if the email unique constraint is violated by a concurrent signup — the
    service layer turns that into a clean `EmailAlreadyRegisteredError`.
    """
    user = User(
        full_name=full_name,
        email=email,
        password_hash=password_hash,
        auth_provider="local",
    )
    db.add(user)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to create user (email=%s).", email)
        raise
    db.refresh(user)  # loads DB-generated defaults: id, created_at, updated_at
    return user


def update_last_login(db: Session, user: User) -> None:
    user.last_login_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to update last_login_at (user_id=%s).", user.id)
        raise


def create_refresh_token_record(
    db: Session, *, user_id: int, token_hash: str, expires_at: datetime
) -> RefreshToken:
    record = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    db.add(record)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to store refresh token (user_id=%s).", user_id)
        raise
    db.refresh(record)
    return record


def get_refresh_token_by_hash(db: Session, token_hash: str) -> RefreshToken | None:
    statement = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    return db.execute(statement).scalar_one_or_none()


def revoke_refresh_token(db: Session, token: RefreshToken) -> None:
    token.revoked_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to revoke refresh token (id=%s).", token.id)
        raise


def revoke_all_user_refresh_tokens(db: Session, user_id: int) -> None:
    """Revoke every still-active refresh token for a user.

    Not called by any endpoint yet — kept available for a future
    "log out of all devices" action, and used by tests to simulate that.
    """
    statement = select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
    now = datetime.now(timezone.utc)
    tokens = db.execute(statement).scalars().all()
    for token in tokens:
        token.revoked_at = now
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to revoke all refresh tokens (user_id=%s).", user_id)
        raise
