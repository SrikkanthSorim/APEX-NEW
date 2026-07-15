"""FastAPI application entrypoint.

Run locally with::

    uvicorn app.main:app --reload --reload-dir app --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.utility_router import utility_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging_config import configure_logging

configure_logging()

app = FastAPI(title=settings.app_name)

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
