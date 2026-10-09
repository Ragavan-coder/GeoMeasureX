"""
GeoMeasureX - File Schemas

Pydantic models for file upload/detail API responses.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    """Response after successful file upload."""

    id: str = Field(..., description="Unique file identifier (UUID)")
    filename: str = Field(..., description="Sanitized filename")
    status: str = Field(..., description="Processing status: PENDING, PROCESSING, COMPLETED, FAILED")

    model_config = {"json_schema_extra": {
        "examples": [{
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "filename": "survey.kml",
            "status": "PROCESSING",
        }]
    }}


class FileDetailResponse(BaseModel):
    """Detailed file information including processing results."""

    id: str
    filename: str
    original_filename: str
    file_type: Optional[str] = Field(None, description="KML or SHAPEFILE")
    feature_count: Optional[int] = None
    source_crs: Optional[str] = Field(None, description="Detected source CRS (e.g., EPSG:4326)")
    measurement_crs: Optional[str] = Field(None, description="CRS used for measurements (e.g., EPSG:32644)")
    crs_strategy: Optional[str] = Field(None, description="How the measurement CRS was selected")
    status: str
    processing_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    file_size_bytes: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FileListResponse(BaseModel):
    """List of file records."""

    files: list[FileDetailResponse]
    total: int
