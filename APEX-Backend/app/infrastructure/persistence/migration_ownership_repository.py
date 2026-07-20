"""Tracks which user owns each filesystem-stored migration job.

Migration job data itself is unchanged — it still lives on disk as JSON
reports under `storage/migration-jobs/<jobId>/` (see
`app.infrastructure.persistence.job_repository.JobRepository`). This
repository only answers "which user created job X", recorded once at job
creation time (`POST /api/v1/connect`) and checked by every job-scoped
endpoint afterward (see `app.api.deps.verify_job_ownership`).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models import MigrationJobOwner

logger = logging.getLogger(__name__)


def record_job_owner(db: Session, *, job_id: str, user_id: int) -> None:
    """Called once, immediately after a job is created in POST /connect."""
    owner = MigrationJobOwner(job_id=job_id, user_id=user_id)
    db.add(owner)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to record job owner (job_id=%s).", job_id)
        raise


def get_job_owner_user_id(db: Session, job_id: str) -> int | None:
    """Returns the owning user's id, or None if the job has no owner record."""
    statement = select(MigrationJobOwner.user_id).where(MigrationJobOwner.job_id == job_id)
    return db.execute(statement).scalar_one_or_none()
