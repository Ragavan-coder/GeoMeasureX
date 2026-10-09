"""
GeoMeasureX - Feature Schemas

Pydantic models for geometry feature API responses.
"""

from typing import Optional, Any
from pydantic import BaseModel, Field


class FeatureValidation(BaseModel):
    """Geometry validation details for a feature."""

    is_valid: Optional[bool] = None
    validity_reason: Optional[str] = None
    is_empty: Optional[bool] = None
    repair_attempted: bool = False
    repair_successful: Optional[bool] = None


class FeatureResponse(BaseModel):
    """Single feature with geometry, properties, and validation status."""

    id: str
    feature_index: int = Field(..., description="Zero-based index within the file")
    geometry_type: Optional[str] = Field(None, description="Point, LineString, Polygon, Multi*, etc.")
    geometry_geojson: Optional[Any] = Field(None, description="Geometry as GeoJSON object")
    bbox: Optional[list[float]] = Field(None, description="Bounding box [minx, miny, maxx, maxy]")
    properties: Optional[dict[str, Any]] = Field(None, description="Feature attributes from source file")
    source_crs: Optional[str] = None
    validation: FeatureValidation
    measurement_status: Optional[str] = Field(
        None,
        description="MEASURED, NOT_APPLICABLE, UNSUPPORTED, SKIPPED, FAILED",
    )

    model_config = {"from_attributes": True}


class FeatureListResponse(BaseModel):
    """List of features for a file."""

    file_id: str
    features: list[FeatureResponse]
    total: int
