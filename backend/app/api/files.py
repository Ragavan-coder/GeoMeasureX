"""
GeoMeasureX - Files API Endpoints

Handles file upload, processing, feature retrieval, measurements,
dataset summary, and file deletion.

All endpoints use structured error responses and proper HTTP status codes.
"""

import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings, Settings
from app.database import get_db
from app.exceptions import GeoMeasureError, FileNotFoundError_
from app.models.file_record import FileRecord, FileStatus
from app.models.feature import Feature
from app.models.measurement import Measurement
from app.schemas.error import ErrorResponse
from app.schemas.feature import FeatureResponse, FeatureListResponse, FeatureValidation
from app.schemas.file import FileUploadResponse, FileDetailResponse, FileListResponse
from app.schemas.measurement import (
    MeasurementResponse,
    MeasurementListResponse,
    DatasetSummaryResponse,
    GeometryDistribution,
    AreaSummary,
    LengthSummary,
    QualitySummary,
    QualityWarning,
    CRSInfo,
    PolygonMeasurementData,
    LineMeasurementData,
)
from app.security import FileValidator
from app.services.processing_service import ProcessingService

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_file_or_404(file_id: str, db: Session) -> FileRecord:
    """Retrieve a FileRecord or raise 404."""
    record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not record:
        raise HTTPException(status_code=404, detail={
            "error": {"code": "FILE_NOT_FOUND", "message": f"File not found: {file_id}"}
        })
    return record


# ═══════════════════════════════════════════════════════════════════
# POST /api/v1/files/  — Upload a file
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/",
    response_model=FileUploadResponse,
    status_code=201,
    summary="Upload a geospatial file",
    description=(
        "Upload a KML file or ZIP archive containing a Shapefile. "
        "The file will be validated, parsed, and processed. "
        "Returns a file ID for tracking."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file type"},
        413: {"model": ErrorResponse, "description": "File too large"},
    },
)
async def upload_file(
    file: UploadFile = File(..., description="KML or ZIP file to process"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Upload and process a geospatial file."""
    try:
        # ── Read file content ────────────────────────────────────
        content = await file.read()
        file_size = len(content)

        # ── Security validation ──────────────────────────────────
        sanitized_name, extension = FileValidator.validate_upload(
            filename=file.filename or "unknown",
            file_size=file_size,
            content_type=file.content_type,
        )

        file_type = FileValidator.determine_file_type(extension)

        # ── Save to disk ─────────────────────────────────────────
        upload_dir = settings.upload_path
        file_path = upload_dir / sanitized_name
        file_path.write_bytes(content)

        # ── Create database record ───────────────────────────────
        file_record = FileRecord(
            filename=sanitized_name,
            original_filename=file.filename or "unknown",
            file_type=file_type,
            file_size_bytes=file_size,
            status=FileStatus.PROCESSING.value,
        )
        db.add(file_record)
        db.commit()
        db.refresh(file_record)

        logger.info(
            f"File uploaded: {file_record.id}",
            extra={
                "file_id": file_record.id,
                "uploaded_filename": sanitized_name,
                "file_type": file_type,
                "size": file_size,
            },
        )

        # ── Process file (synchronous for prototype) ─────────────
        # Future: Send to Celery/RQ task queue
        service = ProcessingService()
        service.process_file(
            file_id=file_record.id,
            file_path=file_path,
            file_type=file_type,
            db=db,
        )

        db.refresh(file_record)

        return FileUploadResponse(
            id=file_record.id,
            filename=file_record.original_filename,
            status=file_record.status,
        )

    except GeoMeasureError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail={
            "error": {"code": "UPLOAD_FAILED", "message": "File upload failed"}
        })


# ═══════════════════════════════════════════════════════════════════
# GET /api/v1/files/  — List all files
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/",
    response_model=FileListResponse,
    summary="List all uploaded files",
    description="Returns all uploaded file records with their processing status.",
)
async def list_files(db: Session = Depends(get_db)):
    """List all uploaded files."""
    records = db.query(FileRecord).order_by(FileRecord.created_at.desc()).all()
    return FileListResponse(
        files=[FileDetailResponse.model_validate(r) for r in records],
        total=len(records),
    )


# ═══════════════════════════════════════════════════════════════════
# GET /api/v1/files/{file_id}  — File details
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/{file_id}",
    response_model=FileDetailResponse,
    summary="Get file details",
    description="Returns detailed information about an uploaded file, including CRS and processing status.",
    responses={404: {"model": ErrorResponse}},
)
async def get_file(file_id: str, db: Session = Depends(get_db)):
    """Get file details by ID."""
    record = _get_file_or_404(file_id, db)
    return FileDetailResponse.model_validate(record)


# ═══════════════════════════════════════════════════════════════════
# GET /api/v1/files/{file_id}/features  — Feature list
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/{file_id}/features",
    response_model=FeatureListResponse,
    summary="Get all features",
    description="Returns all geometry features extracted from the file with validation status.",
    responses={404: {"model": ErrorResponse}},
)
async def get_features(file_id: str, db: Session = Depends(get_db)):
    """Get all features for a file."""
    _get_file_or_404(file_id, db)
    features = (
        db.query(Feature)
        .filter(Feature.file_id == file_id)
        .order_by(Feature.feature_index)
        .all()
    )

    feature_responses = []
    for f in features:
        geojson = None
        if f.geometry_geojson:
            try:
                geojson = json.loads(f.geometry_geojson)
            except (json.JSONDecodeError, TypeError):
                geojson = None

        bbox = None
        if f.bbox:
            try:
                bbox = json.loads(f.bbox)
            except (json.JSONDecodeError, TypeError):
                bbox = None

        feature_responses.append(FeatureResponse(
            id=f.id,
            feature_index=f.feature_index,
            geometry_type=f.geometry_type,
            geometry_geojson=geojson,
            bbox=bbox,
            properties=f.properties,
            source_crs=f.source_crs,
            validation=FeatureValidation(
                is_valid=f.is_valid,
                validity_reason=f.validity_reason,
                is_empty=f.is_empty,
                repair_attempted=f.repair_attempted,
                repair_successful=f.repair_successful,
            ),
            measurement_status=f.measurement_status,
        ))

    return FeatureListResponse(
        file_id=file_id,
        features=feature_responses,
        total=len(feature_responses),
    )


# ═══════════════════════════════════════════════════════════════════
# GET /api/v1/files/{file_id}/measurements  — Measurements
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/{file_id}/measurements",
    response_model=MeasurementListResponse,
    summary="Get all measurements",
    description=(
        "Returns calculated measurements for all features. "
        "Polygon areas in m²/hectares/km², line lengths in m/km."
    ),
    responses={404: {"model": ErrorResponse}},
)
async def get_measurements(file_id: str, db: Session = Depends(get_db)):
    """Get all measurements for a file."""
    _get_file_or_404(file_id, db)
    features = (
        db.query(Feature)
        .filter(Feature.file_id == file_id)
        .order_by(Feature.feature_index)
        .all()
    )

    measurements = []
    for f in features:
        m = f.measurement

        polygon_data = None
        line_data = None
        warnings = []

        if m:
            if m.area_m2 is not None:
                polygon_data = PolygonMeasurementData(
                    area_m2=round(m.area_m2, 6),
                    area_hectares=round(m.area_hectares, 6) if m.area_hectares else 0,
                    area_km2=round(m.area_km2, 6) if m.area_km2 else 0,
                    perimeter_m=round(m.perimeter_m, 2) if m.perimeter_m else None,
                )
            if m.length_m is not None:
                line_data = LineMeasurementData(
                    length_m=round(m.length_m, 6),
                    length_km=round(m.length_km, 6) if m.length_km else 0,
                )
            if m.warnings:
                warnings = [
                    QualityWarning(**w) if isinstance(w, dict) else w
                    for w in m.warnings
                ]

        measurements.append(MeasurementResponse(
            feature_id=f.id,
            feature_index=f.feature_index,
            geometry_type=f.geometry_type,
            source_crs=f.source_crs,
            measurement_crs=m.measurement_crs if m else None,
            crs_strategy=m.crs_strategy if m else None,
            measurement_status=f.measurement_status,
            polygon_measurement=polygon_data,
            line_measurement=line_data,
            quality={
                "valid": f.is_valid,
                "repaired": f.repair_attempted and (f.repair_successful or False),
            },
            warnings=warnings,
        ))

    return MeasurementListResponse(
        file_id=file_id,
        measurements=measurements,
        total=len(measurements),
    )


# ═══════════════════════════════════════════════════════════════════
# GET /api/v1/files/{file_id}/summary  — Dataset summary
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/{file_id}/summary",
    response_model=DatasetSummaryResponse,
    summary="Get dataset summary",
    description=(
        "Returns an aggregate summary: feature counts, geometry distribution, "
        "total/average/min/max measurements, quality stats, and CRS info."
    ),
    responses={404: {"model": ErrorResponse}},
)
async def get_summary(file_id: str, db: Session = Depends(get_db)):
    """Get dataset summary with aggregate statistics."""
    record = _get_file_or_404(file_id, db)
    features = (
        db.query(Feature)
        .filter(Feature.file_id == file_id)
        .all()
    )

    # ── Geometry distribution ────────────────────────────────────
    geo_dist = GeometryDistribution()
    for f in features:
        gt = f.geometry_type or "Unknown"
        if hasattr(geo_dist, gt):
            setattr(geo_dist, gt, getattr(geo_dist, gt) + 1)
        else:
            geo_dist.Unknown += 1

    # ── Area summary ─────────────────────────────────────────────
    polygon_areas = []
    for f in features:
        if f.measurement and f.measurement.area_m2 is not None:
            polygon_areas.append(f.measurement.area_m2)

    area_summary = AreaSummary(polygon_count=len(polygon_areas))
    if polygon_areas:
        area_summary.total_area_m2 = sum(polygon_areas)
        area_summary.total_area_hectares = area_summary.total_area_m2 / 10_000
        area_summary.total_area_km2 = area_summary.total_area_m2 / 1_000_000
        area_summary.average_area_m2 = area_summary.total_area_m2 / len(polygon_areas)
        area_summary.largest_area_m2 = max(polygon_areas)
        area_summary.smallest_area_m2 = min(polygon_areas)

    # ── Length summary ───────────────────────────────────────────
    line_lengths = []
    for f in features:
        if f.measurement and f.measurement.length_m is not None:
            line_lengths.append(f.measurement.length_m)

    length_summary = LengthSummary(line_count=len(line_lengths))
    if line_lengths:
        length_summary.total_length_m = sum(line_lengths)
        length_summary.total_length_km = length_summary.total_length_m / 1_000
        length_summary.average_length_m = length_summary.total_length_m / len(line_lengths)
        length_summary.longest_m = max(line_lengths)
        length_summary.shortest_m = min(line_lengths)

    # ── Quality summary ──────────────────────────────────────────
    all_warnings = []
    invalid_count = 0
    repaired_count = 0
    unsupported_count = 0
    empty_count = 0

    for f in features:
        if f.is_valid is False:
            invalid_count += 1
        if f.repair_attempted and f.repair_successful:
            repaired_count += 1
        if f.measurement_status == "UNSUPPORTED":
            unsupported_count += 1
        if f.is_empty:
            empty_count += 1
        if f.measurement and f.measurement.warnings:
            for w in f.measurement.warnings:
                if isinstance(w, dict):
                    all_warnings.append(QualityWarning(**w))

    quality_summary = QualitySummary(
        invalid_feature_count=invalid_count,
        repaired_feature_count=repaired_count,
        unsupported_feature_count=unsupported_count,
        empty_feature_count=empty_count,
        warning_count=len(all_warnings),
        warnings=all_warnings,
    )

    # ── CRS info ─────────────────────────────────────────────────
    crs_info = CRSInfo(
        source_crs=record.source_crs,
        measurement_crs=record.measurement_crs,
        crs_strategy=record.crs_strategy,
        is_geographic=record.source_crs == "EPSG:4326" if record.source_crs else None,
    )

    return DatasetSummaryResponse(
        file_id=record.id,
        filename=record.original_filename,
        file_type=record.file_type,
        status=record.status,
        feature_count=len(features),
        processing_time_ms=record.processing_time_ms,
        geometry_distribution=geo_dist,
        area_summary=area_summary,
        length_summary=length_summary,
        quality=quality_summary,
        crs=crs_info,
    )


# ═══════════════════════════════════════════════════════════════════
# DELETE /api/v1/files/{file_id}  — Delete a file
# ═══════════════════════════════════════════════════════════════════

@router.delete(
    "/{file_id}",
    status_code=204,
    summary="Delete a file",
    description="Deletes a file record and all associated features and measurements.",
    responses={404: {"model": ErrorResponse}},
)
async def delete_file(file_id: str, db: Session = Depends(get_db)):
    """Delete a file and all associated data."""
    record = _get_file_or_404(file_id, db)

    # Delete the uploaded file from disk
    settings = get_settings()
    file_path = settings.upload_path / record.filename
    if file_path.exists():
        try:
            file_path.unlink()
        except Exception as e:
            logger.warning(f"Could not delete file from disk: {e}")

    # Delete from database (cascades to features and measurements)
    db.delete(record)
    db.commit()

    logger.info(f"File deleted: {file_id}")
