"""Aggregates all v1 endpoint routers.

Connect and Discovery endpoints are wired. Later stages (strategy, migration,
result) register their routers here.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import connect_controller, discovery_controller

api_router = APIRouter()
api_router.include_router(connect_controller.router)
api_router.include_router(discovery_controller.router)
