"""
GeoMeasureX - Security Module

File upload validation and sanitization.
All uploaded files are treated as untrusted input.

Security Measures:
    - File extension validation
    - File size validation
    - MIME type checking (basic)
    - Filename sanitization (remove path components, special chars)
    - No shell execution with user input
    - No arbitrary file system access
"""

import logging
import re
import uuid
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.exceptions import InvalidFileTypeError, FileTooLargeError

logger = logging.getLogger(__name__)


class FileValidator:
    """
    Validates uploaded files for security and correctness.

    Checks:
        1. File extension (.kml or .zip only)
        2. File size (configurable maximum)
        3. Filename sanitization
    """

    ALLOWED_EXTENSIONS = {".kml", ".zip"}

    # Basic MIME type mapping for validation
    EXPECTED_MIMES = {
        ".kml": [
            "application/vnd.google-earth.kml+xml",
            "application/xml",
            "text/xml",
            "application/octet-stream",  # Many clients send this
        ],
        ".zip": [
            "application/zip",
            "application/x-zip-compressed",
            "application/octet-stream",
            "multipart/x-zip",
        ],
    }

    @classmethod
    def validate_upload(
        cls,
        filename: str,
        file_size: int,
        content_type: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Validate an uploaded file.

        Args:
            filename: Original filename from the upload.
            file_size: Size of the file in bytes.
            content_type: MIME type from the upload headers.

        Returns:
            Tuple of (sanitized_filename, file_extension).

        Raises:
            InvalidFileTypeError: If file type is not supported.
            FileTooLargeError: If file exceeds size limit.
        """
        settings = get_settings()

        # ── Extension check ──────────────────────────────────────
        ext = cls._get_extension(filename)
        if ext not in cls.ALLOWED_EXTENSIONS:
            raise InvalidFileTypeError(
                filename=filename,
                allowed=list(cls.ALLOWED_EXTENSIONS),
            )

        # ── Size check ───────────────────────────────────────────
        if file_size > settings.max_upload_size_bytes:
            raise FileTooLargeError(
                size_bytes=file_size,
                max_bytes=settings.max_upload_size_bytes,
            )

        # ── MIME type check (soft — log warning, don't reject) ───
        if content_type:
            expected = cls.EXPECTED_MIMES.get(ext, [])
            if expected and content_type not in expected:
                logger.warning(
                    f"Unexpected MIME type: {content_type} for extension {ext}",
                    extra={"filename": filename, "content_type": content_type},
                )

        # ── Sanitize filename ────────────────────────────────────
        sanitized = cls.sanitize_filename(filename)

        logger.info(
            f"File validated: {sanitized} ({file_size} bytes)",
            extra={"original": filename, "sanitized": sanitized, "size": file_size},
        )

        return sanitized, ext

    @staticmethod
    def _get_extension(filename: str) -> str:
        """Extract lowercase file extension."""
        return Path(filename).suffix.lower()

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize a filename to prevent path traversal and special character issues.

        Rules:
            - Strip directory components (use basename only)
            - Remove special characters except alphanumeric, dash, underscore, dot
            - Prepend a UUID prefix for uniqueness
            - Limit length
        """
        # Take basename only (remove directory components)
        name = Path(filename).name

        # Remove potentially dangerous characters
        name = re.sub(r'[^\w\-.]', '_', name)

        # Remove leading dots (hidden files)
        name = name.lstrip('.')

        # Limit length
        if len(name) > 200:
            ext = Path(name).suffix
            name = name[:200 - len(ext)] + ext

        # Prepend UUID for uniqueness
        unique_name = f"{uuid.uuid4().hex[:12]}_{name}"

        return unique_name

    @classmethod
    def determine_file_type(cls, extension: str) -> str:
        """Map file extension to FileType."""
        mapping = {
            ".kml": "KML",
            ".zip": "SHAPEFILE",
        }
        return mapping.get(extension, "UNKNOWN")
