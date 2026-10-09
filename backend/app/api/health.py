"""
GeoMeasureX - Health Check Endpoint

Simple health check for monitoring and Docker health checks.
"""

from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()


@router.get(
    "/health",
    summary="Health Check",
    description="Returns the service health status and current timestamp.",
    response_model=dict,
)
async def health_check():
    """Health check endpoint for monitoring and container orchestration."""
    return {
        "status": "healthy",
        "service": "GeoMeasureX",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
