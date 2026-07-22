"""FastAPI application entrypoint.

Run locally with::

    uvicorn app.main:app --reload --reload-dir app --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.utility_router import utility_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.infrastructure.persistence.database import (
    Base,
    engine,
    ensure_database_exists,
    verify_database_connection,
)

# Import every ORM model module here so `Base.metadata` knows about all
# tables before `create_all()` runs below — SQLAlchemy only creates tables
# for model classes that have actually been imported (their class body must
# have executed at least once). `noqa: F401` because this import is only for
# its import-time side effect, not for anything used by name in this file.
from app.infrastructure.persistence import models as _persistence_models  # noqa: F401

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup/shutdown hook — runs once when the server boots.

    For a Java developer: this is roughly the FastAPI equivalent of a Spring
    Boot `ApplicationRunner`/`@PostConstruct` block that runs once at boot,
    before any request is served.
    """
    settings.validate_auth_settings()
    # Local/dev convenience: create the target database itself if it doesn't
    # exist yet (the PostgreSQL user/role must already exist and have
    # CREATEDB — this does not create roles, only the database).
    ensure_database_exists()
    verify_database_connection()
    # Creates any tables that don't exist yet. Never drops or alters an
    # existing table, and never touches existing rows — safe to run on every
    # startup. Alembic is intentionally not used yet (see requirements.txt).
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/created.")
    yield
    # (nothing to clean up on shutdown today)


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All v1 endpoints are mounted under /api/v1 (-> POST /api/v1/connect).
app.include_router(api_router, prefix=settings.api_v1_prefix)

# Unversioned utility endpoints the frontend calls directly under /api
# (-> GET /api/github/repo-visibility, GET /api/local-project/capabilities).
app.include_router(utility_router, prefix="/api")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok", "service": settings.app_name}
