"""Database access for OAuth-linked accounts (Google/GitHub social login).

Same shape as `user_repository.py`: plain `Session` in, ORM objects (or
`None`) out, no HTTP concerns. The find-or-create-or-link decision logic
that calls these lives in
`app.application.services.auth_service.AuthService.authenticate_with_oauth`.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models import OAuthAccount, User

logger = logging.getLogger(__name__)


def get_oauth_account(db: Session, *, provider: str, provider_user_id: str) -> OAuthAccount | None:
    statement = select(OAuthAccount).where(
        OAuthAccount.provider == provider,
        OAuthAccount.provider_user_id == provider_user_id,
    )
    return db.execute(statement).scalar_one_or_none()


def create_oauth_account(
    db: Session,
    *,
    user_id: int,
    provider: str,
    provider_user_id: str,
    provider_email: str | None,
) -> OAuthAccount:
    """Insert a new provider-identity link for an existing user.

    Raises `sqlalchemy.exc.IntegrityError` if `(provider, provider_user_id)`
    is already linked (a concurrent login for the same provider account) —
    the service layer treats that as "someone else just created it, re-read
    it" rather than a hard failure.
    """
    account = OAuthAccount(
        user_id=user_id,
        provider=provider,
        provider_user_id=provider_user_id,
        provider_email=provider_email,
    )
    db.add(account)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception(
            "Failed to create oauth account (provider=%s, user_id=%s).", provider, user_id
        )
        raise
    db.refresh(account)
    return account


def create_oauth_user(
    db: Session,
    *,
    full_name: str,
    email: str,
    auth_provider: str,
    provider_user_id: str,
    profile_image: str | None,
    is_email_verified: bool,
) -> User:
    """Insert a brand-new OAuth-only user: `password_hash` stays NULL,
    `is_active` is always True (there is no email-confirmation gate for an
    OAuth signup — the provider already vouched for the account)."""
    user = User(
        full_name=full_name,
        email=email,
        password_hash=None,
        auth_provider=auth_provider,
        provider_user_id=provider_user_id,
        profile_image=profile_image,
        is_active=True,
        is_email_verified=is_email_verified,
    )
    db.add(user)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception(
            "Failed to create OAuth user (email=%s, provider=%s).", email, auth_provider
        )
        raise
    db.refresh(user)
    return user
