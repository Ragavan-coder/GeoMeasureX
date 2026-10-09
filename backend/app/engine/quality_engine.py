"""
GeoMeasureX - Quality Engine

Performs measurement quality checks and generates structured warnings.
Detects zero-area polygons, extremely small/large geometries, zero-length
lines, missing CRS, and other data quality issues.

Each warning includes:
    - severity: WARNING, ERROR, or INFO
    - code: Machine-readable code for programmatic handling
    - message: Human-readable description
    - details: Additional context
"""

import logging
from typing import Optional, Any

from shapely.geometry.base import BaseGeometry

logger = logging.getLogger(__name__)


class QualityWarning:
    """Represents a single quality check warning."""

    def __init__(
        self,
        severity: str,
        code: str,
        message: str,
        feature_index: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        self.severity = severity
        self.code = code
        self.message = message
        self.feature_index = feature_index
        self.details = details or {}

    def to_dict(self) -> dict:
        result = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.feature_index is not None:
            result["feature_index"] = self.feature_index
        if self.details:
            result["details"] = self.details
        return result


class QualityEngine:
    """
    Runs quality checks on measured geometries and generates warnings.

    Thresholds:
        - Zero area: area_m2 < 0.01 m²
        - Tiny polygon: area_m2 < 1.0 m²
        - Huge polygon: area_m2 > 1,000,000 km² (larger than any country)
        - Zero length: length_m < 0.001 m
        - Tiny line: length_m < 0.1 m
        - Huge line: length_m > 40,075 km (Earth's circumference)
    """

    # ── Thresholds ───────────────────────────────────────────────
    ZERO_AREA_THRESHOLD_M2: float = 0.01
    TINY_POLYGON_THRESHOLD_M2: float = 1.0
    HUGE_POLYGON_THRESHOLD_M2: float = 1_000_000_000_000  # 1M km²

    ZERO_LENGTH_THRESHOLD_M: float = 0.001
    TINY_LINE_THRESHOLD_M: float = 0.1
    HUGE_LINE_THRESHOLD_M: float = 40_075_000  # Earth circumference

    @classmethod
    def check_polygon(
        cls,
        area_m2: float,
        feature_index: int,
        is_valid: bool = True,
        was_repaired: bool = False,
    ) -> list[QualityWarning]:
        """Run quality checks on a polygon measurement."""
        warnings: list[QualityWarning] = []

        if area_m2 < cls.ZERO_AREA_THRESHOLD_M2:
            warnings.append(QualityWarning(
                severity="WARNING",
                code="ZERO_AREA_GEOMETRY",
                message="Polygon has zero or near-zero measurable area",
                feature_index=feature_index,
                details={"area_m2": area_m2},
            ))
        elif area_m2 < cls.TINY_POLYGON_THRESHOLD_M2:
            warnings.append(QualityWarning(
                severity="INFO",
                code="TINY_POLYGON",
                message=f"Polygon area is very small ({area_m2:.4f} m²)",
                feature_index=feature_index,
                details={"area_m2": area_m2},
            ))

        if area_m2 > cls.HUGE_POLYGON_THRESHOLD_M2:
            warnings.append(QualityWarning(
                severity="WARNING",
                code="EXTREMELY_LARGE_POLYGON",
                message=f"Polygon area is extremely large ({area_m2 / 1e6:.0f} km²)",
                feature_index=feature_index,
                details={"area_m2": area_m2, "area_km2": area_m2 / 1_000_000},
            ))

        if not is_valid:
            warnings.append(QualityWarning(
                severity="WARNING",
                code="INVALID_GEOMETRY_MEASURED",
                message="Measurement performed on invalid geometry (repair unsuccessful)",
                feature_index=feature_index,
            ))

        if was_repaired:
            warnings.append(QualityWarning(
                severity="INFO",
                code="GEOMETRY_REPAIRED",
                message="Measurement performed on repaired geometry",
                feature_index=feature_index,
            ))

        return warnings

    @classmethod
    def check_line(
        cls,
        length_m: float,
        feature_index: int,
        is_valid: bool = True,
        was_repaired: bool = False,
    ) -> list[QualityWarning]:
        """Run quality checks on a line measurement."""
        warnings: list[QualityWarning] = []

        if length_m < cls.ZERO_LENGTH_THRESHOLD_M:
            warnings.append(QualityWarning(
                severity="WARNING",
                code="ZERO_LENGTH_GEOMETRY",
                message="Line has zero or near-zero measurable length",
                feature_index=feature_index,
                details={"length_m": length_m},
            ))
        elif length_m < cls.TINY_LINE_THRESHOLD_M:
            warnings.append(QualityWarning(
                severity="INFO",
                code="TINY_LINE",
                message=f"Line length is very small ({length_m:.4f} m)",
                feature_index=feature_index,
                details={"length_m": length_m},
            ))

        if length_m > cls.HUGE_LINE_THRESHOLD_M:
            warnings.append(QualityWarning(
                severity="WARNING",
                code="EXTREMELY_LONG_LINE",
                message=f"Line length exceeds Earth circumference ({length_m / 1000:.0f} km)",
                feature_index=feature_index,
                details={"length_m": length_m, "length_km": length_m / 1000},
            ))

        if not is_valid:
            warnings.append(QualityWarning(
                severity="WARNING",
                code="INVALID_GEOMETRY_MEASURED",
                message="Measurement performed on invalid geometry",
                feature_index=feature_index,
            ))

        if was_repaired:
            warnings.append(QualityWarning(
                severity="INFO",
                code="GEOMETRY_REPAIRED",
                message="Measurement performed on repaired geometry",
                feature_index=feature_index,
            ))

        return warnings

    @classmethod
    def check_crs(
        cls,
        source_crs: Optional[str],
        is_geographic: bool = False,
    ) -> list[QualityWarning]:
        """Run CRS-related quality checks."""
        warnings: list[QualityWarning] = []

        if source_crs is None:
            warnings.append(QualityWarning(
                severity="WARNING",
                code="MISSING_CRS",
                message="No CRS information found; defaulting to EPSG:4326",
            ))

        if is_geographic:
            warnings.append(QualityWarning(
                severity="INFO",
                code="GEOGRAPHIC_CRS_DETECTED",
                message="Source CRS uses geographic coordinates (degrees); "
                        "measurements performed in projected CRS",
                details={"source_crs": source_crs},
            ))

        return warnings

    @classmethod
    def check_empty_geometry(cls, feature_index: int) -> QualityWarning:
        """Warning for empty geometry."""
        return QualityWarning(
            severity="WARNING",
            code="EMPTY_GEOMETRY",
            message="Feature contains an empty geometry",
            feature_index=feature_index,
        )

    @classmethod
    def check_null_geometry(cls, feature_index: int) -> QualityWarning:
        """Warning for null geometry."""
        return QualityWarning(
            severity="ERROR",
            code="NULL_GEOMETRY",
            message="Feature contains a null geometry",
            feature_index=feature_index,
        )

    @classmethod
    def check_unsupported_geometry(
        cls, geometry_type: str, feature_index: int
    ) -> QualityWarning:
        """Warning for unsupported geometry types."""
        return QualityWarning(
            severity="INFO",
            code="UNSUPPORTED_GEOMETRY_TYPE",
            message=f"Geometry type '{geometry_type}' is not supported for measurement",
            feature_index=feature_index,
            details={"geometry_type": geometry_type},
        )
