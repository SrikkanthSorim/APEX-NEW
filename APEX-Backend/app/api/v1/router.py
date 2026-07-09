"""Aggregates all v1 endpoint routers.

Connect, Discovery, and Migration Config endpoints are wired. Later stages
(strategy, start-migration, result) register their routers here.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    connect_controller,
    discovery_controller,
    migration_config_controller,
    migration_execution_controller,
)

api_router = APIRouter()
api_router.include_router(connect_controller.router)
api_router.include_router(discovery_controller.router)
api_router.include_router(migration_config_controller.router)
api_router.include_router(migration_execution_controller.router)
