"""
GeoMeasureX - API Router

Central router that mounts all API endpoints under /api/v1.
"""

from fastapi import APIRouter

from app.api.files import router as files_router
from app.api.health import router as health_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(files_router, prefix="/files", tags=["Files"])
api_router.include_router(health_router, tags=["Health"])
