"""
GeoMeasureX - Main Application

FastAPI application entry point. Configures CORS, exception handlers,
mounts the API router, and initializes the database on startup.
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import get_settings
from app.database import create_tables
from app.exceptions import GeoMeasureError


# ── Logging Configuration ────────────────────────────────────────────

def setup_logging():
    """Configure structured logging."""
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


# ── Application Lifespan ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Startup
    logger.info("🚀 GeoMeasureX starting up...")
    create_tables()
    settings = get_settings()
    settings.temp_path  # Ensure temp directory exists
    settings.upload_path  # Ensure upload directory exists
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Database: {settings.DATABASE_URL}")
    logger.info(f"Max upload size: {settings.MAX_UPLOAD_SIZE_MB} MB")

    yield

    # Shutdown
    logger.info("GeoMeasureX shutting down...")


# ── FastAPI Application ─────────────────────────────────────────────

app = FastAPI(
    title="GeoMeasureX",
    description=(
        "Intelligent Geospatial File Measurement & Validation API.\n\n"
        "Accept KML files and ZIP archives containing Shapefiles, validate and parse "
        "their geospatial content, correctly handle CRS transformations, calculate "
        "physically meaningful measurements, detect geometry/data quality issues, "
        "and generate detailed measurement reports.\n\n"
        "## Key Features\n"
        "- **KML & Shapefile Support**: Upload `.kml` files or `.zip` archives containing Shapefiles\n"
        "- **CRS Intelligence**: Automatic detection and transformation to appropriate projected CRS\n"
        "- **Accurate Measurements**: Area (m², hectares, km²) and length (m, km) from projected coordinates\n"
        "- **Geometry Validation**: OGC validity checks with automatic repair via `make_valid`\n"
        "- **Quality Engine**: Structured warnings for zero-area, tiny/huge geometries, missing CRS\n"
        "- **GeoJSON Output**: Feature geometries serialized as valid GeoJSON for map visualization\n"
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── CORS ─────────────────────────────────────────────────────────────

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173", "http://localhost:5174", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Exception Handlers ──────────────────────────────────────────────

@app.exception_handler(GeoMeasureError)
async def geomeasure_error_handler(request: Request, exc: GeoMeasureError):
    """Handle all GeoMeasureX domain exceptions with structured JSON."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    """Catch-all: never leak stack traces to clients."""
    logger = logging.getLogger(__name__)
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
            }
        },
    )


# ── Mount API Router ────────────────────────────────────────────────

app.include_router(api_router)
