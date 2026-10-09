"""
GeoMeasureX - Measurement Schemas

Pydantic models for measurement results and dataset summary API responses.
"""

from typing import Optional, Any
from pydantic import BaseModel, Field


class QualityWarning(BaseModel):
    """A single quality check warning."""

    severity: str = Field(..., description="WARNING, ERROR, or INFO")
    code: str = Field(..., description="Machine-readable warning code")
    message: str = Field(..., description="Human-readable warning description")
    feature_id: Optional[int] = None
    details: Optional[dict[str, Any]] = None


class PolygonMeasurementData(BaseModel):
    """Area measurements for polygon geometries."""

    area_m2: float = Field(..., description="Area in square meters")
    area_hectares: float = Field(..., description="Area in hectares (1 ha = 10,000 m²)")
    area_km2: float = Field(..., description="Area in square kilometers")
    perimeter_m: Optional[float] = Field(None, description="Perimeter in meters")


class LineMeasurementData(BaseModel):
    """Length measurements for line geometries."""

    length_m: float = Field(..., description="Length in meters")
    length_km: float = Field(..., description="Length in kilometers")


class MeasurementResponse(BaseModel):
    """Measurement result for a single feature."""

    feature_id: str
    feature_index: int
    geometry_type: Optional[str] = None
    source_crs: Optional[str] = None
    measurement_crs: Optional[str] = None
    crs_strategy: Optional[str] = None
    measurement_status: Optional[str] = None

    # Only one of these will be populated based on geometry type
    polygon_measurement: Optional[PolygonMeasurementData] = None
    line_measurement: Optional[LineMeasurementData] = None

    quality: Optional[dict[str, Any]] = Field(
        None,
        description="Validation status and quality warnings",
    )
    warnings: list[QualityWarning] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class MeasurementListResponse(BaseModel):
    """All measurements for a file."""

    file_id: str
    measurements: list[MeasurementResponse]
    total: int


# ── Dataset Summary ──────────────────────────────────────────────────

class GeometryDistribution(BaseModel):
    """Count of features by geometry type."""

    Point: int = 0
    LineString: int = 0
    Polygon: int = 0
    MultiPoint: int = 0
    MultiLineString: int = 0
    MultiPolygon: int = 0
    GeometryCollection: int = 0
    Unknown: int = 0


class AreaSummary(BaseModel):
    """Aggregate area statistics across all polygons."""

    total_area_m2: float = 0.0
    total_area_hectares: float = 0.0
    total_area_km2: float = 0.0
    average_area_m2: float = 0.0
    largest_area_m2: float = 0.0
    smallest_area_m2: float = 0.0
    polygon_count: int = 0


class LengthSummary(BaseModel):
    """Aggregate length statistics across all line features."""

    total_length_m: float = 0.0
    total_length_km: float = 0.0
    average_length_m: float = 0.0
    longest_m: float = 0.0
    shortest_m: float = 0.0
    line_count: int = 0


class QualitySummary(BaseModel):
    """Quality/validation aggregate statistics."""

    invalid_feature_count: int = 0
    repaired_feature_count: int = 0
    unsupported_feature_count: int = 0
    empty_feature_count: int = 0
    warning_count: int = 0
    warnings: list[QualityWarning] = Field(default_factory=list)


class CRSInfo(BaseModel):
    """CRS information for the dataset."""

    source_crs: Optional[str] = None
    measurement_crs: Optional[str] = None
    crs_strategy: Optional[str] = None
    is_geographic: Optional[bool] = None


class DatasetSummaryResponse(BaseModel):
    """Complete dataset summary with measurements, quality, and CRS info."""

    file_id: str
    filename: str
    file_type: Optional[str] = None
    status: str
    feature_count: int = 0
    processing_time_ms: Optional[float] = None

    geometry_distribution: GeometryDistribution = Field(default_factory=GeometryDistribution)
    area_summary: AreaSummary = Field(default_factory=AreaSummary)
    length_summary: LengthSummary = Field(default_factory=LengthSummary)
    quality: QualitySummary = Field(default_factory=QualitySummary)
    crs: CRSInfo = Field(default_factory=CRSInfo)
