"""
GeoMeasureX - Structured Exception Classes

Production-quality error handling with error codes, HTTP status mapping,
and structured JSON responses. Never exposes stack traces to API clients.
"""

from typing import Optional


class GeoMeasureError(Exception):
    """Base exception for all GeoMeasureX errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: Optional[dict] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        result = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        if self.details:
            result["error"]["details"] = self.details
        return result


# ── File Upload Errors ───────────────────────────────────────────────

class InvalidFileTypeError(GeoMeasureError):
    """Uploaded file type is not supported."""

    def __init__(self, filename: str, allowed: list[str] | None = None):
        super().__init__(
            code="INVALID_FILE_TYPE",
            message=f"File type not supported: {filename}",
            status_code=400,
            details={"filename": filename, "allowed_types": allowed or [".kml", ".zip"]},
        )


class FileTooLargeError(GeoMeasureError):
    """Uploaded file exceeds maximum size limit."""

    def __init__(self, size_bytes: int, max_bytes: int):
        super().__init__(
            code="FILE_TOO_LARGE",
            message=f"File size {size_bytes} bytes exceeds maximum {max_bytes} bytes",
            status_code=413,
            details={"size_bytes": size_bytes, "max_bytes": max_bytes},
        )


class FileNotFoundError_(GeoMeasureError):
    """Requested file record does not exist."""

    def __init__(self, file_id: str):
        super().__init__(
            code="FILE_NOT_FOUND",
            message=f"File not found: {file_id}",
            status_code=404,
            details={"file_id": file_id},
        )


# ── Archive / Shapefile Errors ───────────────────────────────────────

class CorruptedArchiveError(GeoMeasureError):
    """ZIP archive is corrupted or cannot be read."""

    def __init__(self, reason: str = "Archive is corrupted or unreadable"):
        super().__init__(
            code="CORRUPTED_ARCHIVE",
            message=reason,
            status_code=400,
        )


class InvalidShapefileError(GeoMeasureError):
    """Shapefile dataset is missing required components."""

    def __init__(self, reason: str, missing_files: list[str] | None = None):
        super().__init__(
            code="INVALID_SHAPEFILE",
            message=reason,
            status_code=400,
            details={"missing_files": missing_files or []},
        )


class ZipTraversalError(GeoMeasureError):
    """ZIP archive contains path traversal attack vectors."""

    def __init__(self):
        super().__init__(
            code="ZIP_TRAVERSAL_ATTACK",
            message="Archive contains unsafe file paths (path traversal detected)",
            status_code=400,
        )


# ── KML Errors ───────────────────────────────────────────────────────

class InvalidKMLError(GeoMeasureError):
    """KML file is malformed or unreadable."""

    def __init__(self, reason: str = "KML file is malformed or cannot be parsed"):
        super().__init__(
            code="INVALID_KML",
            message=reason,
            status_code=400,
        )


# ── CRS Errors ───────────────────────────────────────────────────────

class MissingCRSError(GeoMeasureError):
    """CRS could not be determined for the dataset."""

    def __init__(self, reason: str = "Coordinate Reference System could not be determined"):
        super().__init__(
            code="MISSING_CRS",
            message=reason,
            status_code=422,
        )


class CRSTransformationError(GeoMeasureError):
    """CRS transformation failed."""

    def __init__(self, source: str, target: str, reason: str = ""):
        super().__init__(
            code="CRS_TRANSFORMATION_FAILED",
            message=f"Failed to transform from {source} to {target}. {reason}",
            status_code=422,
            details={"source_crs": source, "target_crs": target},
        )


# ── Geometry Errors ──────────────────────────────────────────────────

class EmptyDatasetError(GeoMeasureError):
    """Dataset contains no features."""

    def __init__(self):
        super().__init__(
            code="EMPTY_DATASET",
            message="Dataset contains no features",
            status_code=422,
        )


class UnsupportedGeometryError(GeoMeasureError):
    """Geometry type is not supported for measurement."""

    def __init__(self, geometry_type: str):
        super().__init__(
            code="UNSUPPORTED_GEOMETRY",
            message=f"Geometry type not supported for measurement: {geometry_type}",
            status_code=422,
            details={"geometry_type": geometry_type},
        )


# ── Processing Errors ────────────────────────────────────────────────

class ProcessingError(GeoMeasureError):
    """General processing failure."""

    def __init__(self, reason: str = "File processing failed"):
        super().__init__(
            code="PROCESSING_FAILED",
            message=reason,
            status_code=500,
        )
