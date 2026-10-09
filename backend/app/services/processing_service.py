"""
GeoMeasureX - Processing Service

Orchestrates the complete file processing pipeline:

    UPLOAD → Security → Parse → Validate → CRS → Measure → Quality → Store

This service ties together all engine components and persists results
to the database. For the prototype, processing is synchronous but the
architecture supports async/background workers (Celery/RQ) in the future.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
from pyproj import CRS
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.engine.measurement_engine import MeasurementEngine, DatasetMeasurementResult
from app.exceptions import (
    GeoMeasureError,
    InvalidFileTypeError,
    ProcessingError,
)
from app.models.file_record import FileRecord, FileStatus, FileType
from app.models.feature import Feature
from app.models.measurement import Measurement
from app.parsers.kml_parser import KMLParser
from app.parsers.shapefile_parser import ShapefileParser
from app.security import FileValidator

logger = logging.getLogger(__name__)


class ProcessingService:
    """
    Complete file processing pipeline.

    The pipeline stages:
        1. Security Layer (validate upload)
        2. File Parser (KML or Shapefile)
        3. Measurement Engine (CRS → Validate → Transform → Measure → Quality)
        4. Result Storage (persist to database)

    Future Scope:
        - Replace synchronous processing with Celery/RQ task queue
        - Add cloud object storage (S3/GCS) for file persistence
        - Add WebSocket notifications for processing status
    """

    def __init__(self):
        self.measurement_engine = MeasurementEngine()
        self.settings = get_settings()

    def process_file(
        self,
        file_id: str,
        file_path: Path,
        file_type: str,
        db: Session,
    ) -> None:
        """
        Process an uploaded geospatial file end-to-end.

        Updates the FileRecord status throughout processing:
            PENDING → PROCESSING → COMPLETED/FAILED

        Args:
            file_id: UUID of the FileRecord.
            file_path: Path to the uploaded file on disk.
            file_type: "KML" or "SHAPEFILE".
            db: SQLAlchemy session.
        """
        start_time = time.perf_counter()

        # Update status to PROCESSING
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            logger.error(f"FileRecord not found: {file_id}")
            return

        file_record.status = FileStatus.PROCESSING.value
        db.commit()

        try:
            # ── Stage 1: Parse file ──────────────────────────────
            logger.info(f"Processing file: {file_id} ({file_type})")

            gdf, source_crs = self._parse_file(file_path, file_type)

            # ── Stage 2: Run measurement engine ──────────────────
            result = self.measurement_engine.measure_dataset(gdf, source_crs)

            # ── Stage 3: Persist results ─────────────────────────
            self._persist_results(file_record, result, db)

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # ── Stage 4: Update file record ──────────────────────
            file_record.status = FileStatus.COMPLETED.value
            file_record.feature_count = result.feature_count
            file_record.processing_time_ms = elapsed_ms
            if result.crs_resolution:
                file_record.source_crs = result.crs_resolution.source_epsg
                file_record.measurement_crs = result.crs_resolution.measurement_epsg
                file_record.crs_strategy = result.crs_resolution.strategy

            db.commit()

            logger.info(
                f"File processed successfully: {file_id}",
                extra={
                    "feature_count": result.feature_count,
                    "processing_time_ms": elapsed_ms,
                },
            )

        except GeoMeasureError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            file_record.status = FileStatus.FAILED.value
            file_record.error_message = f"[{e.code}] {e.message}"
            file_record.processing_time_ms = elapsed_ms
            db.commit()
            logger.error(
                f"Processing failed: {e.code} - {e.message}",
                extra={"file_id": file_id},
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            file_record.status = FileStatus.FAILED.value
            file_record.error_message = f"[PROCESSING_FAILED] {str(e)}"
            file_record.processing_time_ms = elapsed_ms
            db.commit()
            logger.exception(f"Unexpected error processing file {file_id}: {e}")

    def _parse_file(
        self, file_path: Path, file_type: str
    ) -> tuple[gpd.GeoDataFrame, Optional[CRS]]:
        """Parse a file based on its type."""
        if file_type == "KML":
            gdf = KMLParser.parse(file_path)
            return gdf, KMLParser.get_source_crs()

        elif file_type == "SHAPEFILE":
            return ShapefileParser.parse(file_path, self.settings.temp_path)

        else:
            raise InvalidFileTypeError(file_path.name)

    def _clean_properties(self, properties: Optional[dict]) -> Optional[dict]:
        if not properties:
            return properties
        cleaned = {}
        for k, v in properties.items():
            try:
                if pd.isna(v):
                    cleaned[k] = None
                else:
                    cleaned[k] = v
            except Exception:
                cleaned[k] = v
        return cleaned

    def _persist_results(
        self,
        file_record: FileRecord,
        result: DatasetMeasurementResult,
        db: Session,
    ) -> None:
        """Persist measurement results to the database."""
        for fm in result.features:
            # Create Feature record
            feature = Feature(
                file_id=file_record.id,
                feature_index=fm.feature_index,
                geometry_type=fm.geometry_type,
                geometry_geojson=json.dumps(fm.geometry_geojson) if fm.geometry_geojson else None,
                bbox=json.dumps(fm.bbox) if fm.bbox else None,
                properties=self._clean_properties(fm.properties),
                source_crs=fm.source_crs,
                is_valid=fm.validation.get("original_valid") if fm.validation else None,
                validity_reason=fm.validation.get("validity_reason") if fm.validation else None,
                is_empty=fm.validation.get("is_empty", False) if fm.validation else False,
                repair_attempted=fm.validation.get("repair_attempted", False) if fm.validation else False,
                repair_successful=fm.validation.get("repair_successful") if fm.validation else None,
                measurement_status=fm.measurement_status,
            )
            db.add(feature)
            db.flush()  # Get the feature.id

            # Create Measurement record (if measurable)
            if fm.measurement_status in ("MEASURED", "NOT_APPLICABLE"):
                measurement = Measurement(
                    feature_id=feature.id,
                    measurement_crs=fm.measurement_crs,
                    crs_strategy=fm.crs_strategy,
                    area_m2=fm.area_m2,
                    area_hectares=fm.area_hectares,
                    area_km2=fm.area_km2,
                    length_m=fm.length_m,
                    length_km=fm.length_km,
                    perimeter_m=fm.perimeter_m,
                    warnings=fm.warnings if fm.warnings else None,
                )
                db.add(measurement)

        db.flush()
