"""Aggregates unversioned utility routers, mounted directly at ``/api``.

These predate the layered ``/api/v1`` endpoints and are kept at their
original (non-versioned) paths so the existing frontend calls
(``/api/github/repo-visibility``, ``/api/local-project/capabilities``,
``/api/java-version-recommendation``) keep working unchanged.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    github_controller,
    java_version_controller,
    local_project_controller,
    migration_preview_controller,
)

utility_router = APIRouter()
utility_router.include_router(github_controller.router)
utility_router.include_router(local_project_controller.router)
utility_router.include_router(java_version_controller.router)
utility_router.include_router(migration_preview_controller.router)
