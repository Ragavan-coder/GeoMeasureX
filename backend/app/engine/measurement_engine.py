"""
GeoMeasureX - Measurement Engine

Orchestrates the complete measurement pipeline:
    CRSResolver → GeometryValidator → Transform → Measure → QualityEngine

This is the core of the system. Every measurement follows this pipeline:
    1. Detect source CRS
    2. Resolve appropriate measurement CRS (UTM / LAEA)
    3. Validate each geometry (and repair if needed)
    4. Transform geometry to the measurement CRS
    5. Calculate physical measurements (area/length) on projected coordinates
    6. Run quality checks
    7. Return structured results

CRITICAL RULES:
    - NEVER measure area/length on geographic coordinates (EPSG:4326)
    - NEVER hard-code measurements
    - NEVER use random values
    - All measurements come from actual geometry.area / geometry.length
    - Maintain full float64 precision internally
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Any

import geopandas as gpd
from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

from app.engine.crs_resolver import CRSResolver, CRSResolution
from app.engine.geometry_validator import GeometryValidator, ValidationResult
from app.engine.quality_engine import QualityEngine, QualityWarning

logger = logging.getLogger(__name__)


# ── Geometry type sets for measurement routing ───────────────────────
POLYGON_TYPES = {"Polygon", "MultiPolygon"}
LINE_TYPES = {"LineString", "MultiLineString"}
POINT_TYPES = {"Point", "MultiPoint"}
SUPPORTED_TYPES = POLYGON_TYPES | LINE_TYPES | POINT_TYPES


@dataclass
class FeatureMeasurement:
    """Measurement result for a single feature."""

    feature_index: int
    geometry_type: Optional[str] = None
    source_crs: Optional[str] = None
    measurement_crs: Optional[str] = None
    crs_strategy: Optional[str] = None

    # Polygon measurements
    area_m2: Optional[float] = None
    area_hectares: Optional[float] = None
    area_km2: Optional[float] = None
    perimeter_m: Optional[float] = None

    # Line measurements
    length_m: Optional[float] = None
    length_km: Optional[float] = None

    # Status
    measurement_status: str = "PENDING"  # MEASURED, NOT_APPLICABLE, UNSUPPORTED, SKIPPED, FAILED

    # Validation
    validation: Optional[dict] = None
    warnings: list[dict] = field(default_factory=list)

    # Geometry for storage (GeoJSON)
    geometry_geojson: Optional[dict] = None
    bbox: Optional[list[float]] = None
    properties: Optional[dict] = None


@dataclass
class DatasetMeasurementResult:
    """Complete measurement results for an entire dataset."""

    features: list[FeatureMeasurement]
    crs_resolution: Optional[CRSResolution] = None
    feature_count: int = 0
    processing_time_ms: float = 0.0
    warnings: list[dict] = field(default_factory=list)


class MeasurementEngine:
    """
    The main measurement engine that orchestrates the full pipeline.

    Architecture:
        MeasurementEngine
            ├── CRSResolver      → Selects appropriate projected CRS
            ├── GeometryValidator → Validates & repairs geometries
            └── QualityEngine     → Generates quality warnings

    Usage:
        engine = MeasurementEngine()
        result = engine.measure_dataset(gdf, source_crs)
    """

    def __init__(self):
        self.crs_resolver = CRSResolver
        self.validator = GeometryValidator
        self.quality = QualityEngine

    def measure_dataset(
        self,
        gdf: gpd.GeoDataFrame,
        source_crs: Optional[CRS] = None,
    ) -> DatasetMeasurementResult:
        """
        Measure all features in a GeoDataFrame.

        Pipeline:
            1. Detect/validate CRS
            2. Resolve measurement CRS
            3. Transform coordinates
            4. Validate each geometry
            5. Measure each geometry
            6. Run quality checks

        Args:
            gdf: GeoDataFrame with geometry column and attributes.
            source_crs: Explicitly provided source CRS (overrides gdf.crs).

        Returns:
            DatasetMeasurementResult with per-feature measurements and warnings.
        """
        start_time = time.perf_counter()
        all_warnings: list[dict] = []
        features: list[FeatureMeasurement] = []

        # ── Step 1: Determine source CRS ─────────────────────────
        effective_crs = source_crs or (CRS(gdf.crs) if gdf.crs else None)

        if effective_crs is None:
            logger.warning("No CRS detected; defaulting to EPSG:4326")
            effective_crs = CRS.from_epsg(4326)
            gdf = gdf.set_crs(epsg=4326)
            all_warnings.extend(
                [w.to_dict() for w in self.quality.check_crs(None)]
            )

        source_epsg = CRSResolver._get_epsg_string(effective_crs)

        # CRS quality checks
        crs_warnings = self.quality.check_crs(
            source_epsg, effective_crs.is_geographic
        )
        all_warnings.extend([w.to_dict() for w in crs_warnings])

        # ── Step 2: Resolve measurement CRS ──────────────────────
        bounds = gdf.total_bounds  # (minx, miny, maxx, maxy)
        crs_resolution = self.crs_resolver.resolve(effective_crs, tuple(bounds))

        logger.info(
            "CRS resolved",
            extra={
                "source": crs_resolution.source_epsg,
                "measurement": crs_resolution.measurement_epsg,
                "strategy": crs_resolution.strategy,
            },
        )

        # ── Step 3: Transform to measurement CRS ────────────────
        try:
            gdf_projected = gdf.to_crs(crs_resolution.measurement_crs)
        except Exception as e:
            logger.error(f"CRS transformation failed: {e}")
            # Return features with FAILED status
            for idx in range(len(gdf)):
                features.append(FeatureMeasurement(
                    feature_index=idx,
                    geometry_type=self._get_geom_type(gdf.geometry.iloc[idx]),
                    source_crs=source_epsg,
                    measurement_status="FAILED",
                    properties=self._extract_properties(gdf, idx),
                ))
            elapsed = (time.perf_counter() - start_time) * 1000
            return DatasetMeasurementResult(
                features=features,
                crs_resolution=crs_resolution,
                feature_count=len(gdf),
                processing_time_ms=elapsed,
                warnings=all_warnings,
            )

        # ── Step 4-6: Validate, Measure, Quality per feature ────
        for idx in range(len(gdf)):
            try:
                fm = self._measure_feature(
                    idx=idx,
                    original_geom=gdf.geometry.iloc[idx],
                    projected_geom=gdf_projected.geometry.iloc[idx],
                    crs_resolution=crs_resolution,
                    source_epsg=source_epsg,
                    row_data=gdf.iloc[idx],
                )
                features.append(fm)
                all_warnings.extend(fm.warnings)
            except Exception as e:
                logger.error(f"Failed to measure feature {idx}: {e}")
                features.append(FeatureMeasurement(
                    feature_index=idx,
                    geometry_type=self._get_geom_type(gdf.geometry.iloc[idx]),
                    source_crs=source_epsg,
                    measurement_status="FAILED",
                    warnings=[{"severity": "ERROR", "code": "MEASUREMENT_FAILED",
                               "message": str(e), "feature_index": idx}],
                    properties=self._extract_properties(gdf, idx),
                ))

        elapsed = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Dataset measurement complete: {len(features)} features in {elapsed:.1f}ms"
        )

        return DatasetMeasurementResult(
            features=features,
            crs_resolution=crs_resolution,
            feature_count=len(features),
            processing_time_ms=elapsed,
            warnings=all_warnings,
        )

    def _measure_feature(
        self,
        idx: int,
        original_geom: Optional[BaseGeometry],
        projected_geom: Optional[BaseGeometry],
        crs_resolution: CRSResolution,
        source_epsg: str,
        row_data: Any,
    ) -> FeatureMeasurement:
        """Measure a single feature through validate → measure → quality."""

        fm = FeatureMeasurement(
            feature_index=idx,
            source_crs=source_epsg,
            measurement_crs=crs_resolution.measurement_epsg,
            crs_strategy=crs_resolution.strategy,
            properties=self._extract_properties_from_row(row_data),
        )

        # Extract GeoJSON from original geometry (source CRS) for display
        if original_geom is not None and not original_geom.is_empty:
            try:
                fm.geometry_geojson = mapping(original_geom)
                fm.bbox = list(original_geom.bounds)
            except Exception:
                pass

        # Get geometry type
        geom_type = self._get_geom_type(projected_geom)
        fm.geometry_type = geom_type

        # ── Validate ─────────────────────────────────────────────
        validation = self.validator.validate(projected_geom, attempt_repair=True)
        fm.validation = validation.to_dict()

        if not validation.usable:
            if validation.is_null:
                fm.measurement_status = "SKIPPED"
                fm.warnings.append(
                    self.quality.check_null_geometry(idx).to_dict()
                )
            elif validation.is_empty:
                fm.measurement_status = "SKIPPED"
                fm.warnings.append(
                    self.quality.check_empty_geometry(idx).to_dict()
                )
            else:
                fm.measurement_status = "SKIPPED"
            return fm

        # Use the validated (possibly repaired) geometry
        geom = validation.final_geometry
        was_repaired = validation.geometry_used == "REPAIRED"

        # ── Measure ──────────────────────────────────────────────
        if geom_type in POLYGON_TYPES:
            fm = self._measure_polygon(fm, geom, idx, was_repaired)
        elif geom_type in LINE_TYPES:
            fm = self._measure_line(fm, geom, idx, was_repaired)
        elif geom_type in POINT_TYPES:
            fm.measurement_status = "NOT_APPLICABLE"
        else:
            fm.measurement_status = "UNSUPPORTED"
            fm.warnings.append(
                self.quality.check_unsupported_geometry(
                    geom_type or "Unknown", idx
                ).to_dict()
            )

        return fm

    def _measure_polygon(
        self,
        fm: FeatureMeasurement,
        geom: BaseGeometry,
        idx: int,
        was_repaired: bool,
    ) -> FeatureMeasurement:
        """
        Calculate polygon area from projected geometry.

        Shapely uses the Shoelace Formula internally:
            Area = ½ |Σ (xᵢ·yᵢ₊₁ - xᵢ₊₁·yᵢ)|

        This only produces correct m² results when coordinates are in
        a projected CRS with meter units.

        Unit conversions:
            hectares = m² / 10,000
            km² = m² / 1,000,000
        """
        area_m2 = geom.area           # Square meters (from projected geometry)
        perimeter_m = geom.length     # Perimeter in meters

        fm.area_m2 = area_m2
        fm.area_hectares = area_m2 / 10_000
        fm.area_km2 = area_m2 / 1_000_000
        fm.perimeter_m = perimeter_m
        fm.measurement_status = "MEASURED"

        # Quality checks
        quality_warnings = self.quality.check_polygon(
            area_m2=area_m2,
            feature_index=idx,
            is_valid=geom.is_valid,
            was_repaired=was_repaired,
        )
        fm.warnings.extend([w.to_dict() for w in quality_warnings])

        return fm

    def _measure_line(
        self,
        fm: FeatureMeasurement,
        geom: BaseGeometry,
        idx: int,
        was_repaired: bool,
    ) -> FeatureMeasurement:
        """
        Calculate line length from projected geometry.

        Shapely computes:
            Length = Σ √((xᵢ₊₁ - xᵢ)² + (yᵢ₊₁ - yᵢ)²)

        This is the Euclidean distance sum of consecutive vertices,
        correct only when coordinates are in a metric projected CRS.

        Unit conversion:
            km = m / 1,000
        """
        length_m = geom.length        # Meters (from projected geometry)

        fm.length_m = length_m
        fm.length_km = length_m / 1_000
        fm.measurement_status = "MEASURED"

        # Quality checks
        quality_warnings = self.quality.check_line(
            length_m=length_m,
            feature_index=idx,
            is_valid=geom.is_valid,
            was_repaired=was_repaired,
        )
        fm.warnings.extend([w.to_dict() for w in quality_warnings])

        return fm

    @staticmethod
    def _get_geom_type(geom: Optional[BaseGeometry]) -> Optional[str]:
        """Safely extract geometry type name."""
        if geom is None:
            return None
        try:
            return geom.geom_type
        except Exception:
            return None

    @staticmethod
    def _extract_properties(gdf: gpd.GeoDataFrame, idx: int) -> dict:
        """Extract non-geometry properties from a GeoDataFrame row."""
        try:
            row = gdf.iloc[idx]
            props = {}
            for col in gdf.columns:
                if col == "geometry":
                    continue
                val = row[col]
                # Convert to JSON-serializable types
                if hasattr(val, 'item'):  # numpy types
                    val = val.item()
                if val is None or (isinstance(val, float) and val != val):  # NaN check
                    val = None
                props[col] = val
            return props
        except Exception:
            return {}

    @staticmethod
    def _extract_properties_from_row(row: Any) -> dict:
        """Extract non-geometry properties from a pandas row."""
        try:
            props = {}
            for key, val in row.items():
                if key == "geometry":
                    continue
                if hasattr(val, 'item'):  # numpy types
                    val = val.item()
                if val is None or (isinstance(val, float) and val != val):  # NaN check
                    val = None
                props[key] = val
            return props
        except Exception:
            return {}
