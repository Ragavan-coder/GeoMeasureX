"""
GeoMeasureX - Error Schemas

Structured error response models for consistent API error handling.
"""

from typing import Optional, Any
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Inner error detail."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    error: ErrorDetail

    model_config = {"json_schema_extra": {
        "examples": [{
            "error": {
                "code": "INVALID_FILE_TYPE",
                "message": "File type not supported: data.csv",
                "details": {"filename": "data.csv", "allowed_types": [".kml", ".zip"]},
            }
        }]
    }}
