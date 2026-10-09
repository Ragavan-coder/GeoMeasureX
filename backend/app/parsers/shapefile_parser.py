"""
GeoMeasureX - Shapefile Parser

Safely extracts and parses Shapefiles from ZIP archives.
Handles companion file verification, CRS detection from .prj files,
and security validation (path traversal protection).

Shapefile Components:
    Required: .shp (geometry), .shx (index), .dbf (attributes)
    Important: .prj (CRS definition in WKT format)
    Optional:  .cpg, .sbn, .sbx, .xml, etc.
"""

import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import geopandas as gpd
from pyproj import CRS

from app.exceptions import (
    CorruptedArchiveError,
    InvalidShapefileError,
    ZipTraversalError,
    EmptyDatasetError,
)
from app.engine.crs_resolver import CRSResolver

logger = logging.getLogger(__name__)


class ShapefileParser:
    """
    Parses Shapefiles from ZIP archives with security and validation.

    Pipeline:
        1. Validate ZIP archive integrity
        2. Check for path traversal attacks
        3. Extract to secure temporary directory
        4. Locate .shp file
        5. Verify required companion files (.shx, .dbf)
        6. Read .prj for CRS information
        7. Load into GeoDataFrame
    """

    REQUIRED_EXTENSIONS = {".shp", ".shx", ".dbf"}
    OPTIONAL_EXTENSIONS = {".prj", ".cpg", ".sbn", ".sbx", ".xml", ".qpj"}

    # Maximum number of files in ZIP to prevent zip bombs
    MAX_ZIP_ENTRIES = 500

    # Maximum total extracted size (100 MB)
    MAX_EXTRACTED_SIZE = 100 * 1024 * 1024

    @classmethod
    def parse(cls, zip_path: Path, temp_dir: Path) -> tuple[gpd.GeoDataFrame, Optional[CRS]]:
        """
        Parse a Shapefile from a ZIP archive.

        Args:
            zip_path: Path to the .zip file.
            temp_dir: Base temporary directory for extraction.

        Returns:
            Tuple of (GeoDataFrame, detected CRS or None).

        Raises:
            CorruptedArchiveError: If ZIP is corrupted.
            ZipTraversalError: If ZIP contains path traversal attacks.
            InvalidShapefileError: If Shapefile is incomplete.
            EmptyDatasetError: If no features found.
        """
        logger.info(f"Parsing Shapefile ZIP: {zip_path.name}")

        # Create isolated extraction directory
        extract_dir = Path(tempfile.mkdtemp(dir=str(temp_dir), prefix="shp_"))

        try:
            # ── Step 1: Validate and extract ZIP ─────────────────
            cls._safe_extract(zip_path, extract_dir)

            # ── Step 2: Locate Shapefile components ──────────────
            shp_path = cls._find_shp_file(extract_dir)
            cls._verify_companions(shp_path)

            # ── Step 3: Detect CRS from .prj ─────────────────────
            detected_crs = cls._detect_crs(shp_path)

            # ── Step 4: Load into GeoDataFrame ───────────────────
            gdf = gpd.read_file(str(shp_path))

            if gdf.empty:
                raise EmptyDatasetError()

            # Apply detected CRS if geopandas didn't pick it up
            if gdf.crs is None and detected_crs is not None:
                gdf = gdf.set_crs(detected_crs)

            logger.info(
                f"Shapefile parsed: {len(gdf)} features",
                extra={
                    "feature_count": len(gdf),
                    "crs": str(detected_crs) if detected_crs else "UNKNOWN",
                },
            )
            return gdf, detected_crs or (CRS(gdf.crs) if gdf.crs else None)

        finally:
            # Cleanup extraction directory
            try:
                shutil.rmtree(extract_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp dir: {e}")

    @classmethod
    def _safe_extract(cls, zip_path: Path, extract_dir: Path) -> None:
        """
        Safely extract ZIP with security checks.

        Security:
            - Validates ZIP file integrity
            - Checks for path traversal attacks (.. in paths, absolute paths)
            - Enforces maximum entry count (zip bomb prevention)
            - Enforces maximum total size
        """
        try:
            zf = zipfile.ZipFile(str(zip_path), 'r')
        except zipfile.BadZipFile:
            raise CorruptedArchiveError("ZIP file is corrupted or not a valid ZIP archive")
        except Exception as e:
            raise CorruptedArchiveError(f"Cannot read ZIP file: {str(e)}")

        with zf:
            entries = zf.infolist()

            # Check entry count
            if len(entries) > cls.MAX_ZIP_ENTRIES:
                raise CorruptedArchiveError(
                    f"ZIP contains {len(entries)} entries (max: {cls.MAX_ZIP_ENTRIES})"
                )

            # Check total size
            total_size = sum(e.file_size for e in entries)
            if total_size > cls.MAX_EXTRACTED_SIZE:
                raise CorruptedArchiveError(
                    f"ZIP extracted size {total_size} bytes exceeds limit "
                    f"({cls.MAX_EXTRACTED_SIZE} bytes)"
                )

            # Security: Check each entry for path traversal
            for entry in entries:
                # Normalize the path
                entry_path = Path(entry.filename)

                # Check for absolute paths
                if entry_path.is_absolute():
                    raise ZipTraversalError()

                # Check for path traversal (..)
                try:
                    resolved = (extract_dir / entry.filename).resolve()
                    if not str(resolved).startswith(str(extract_dir.resolve())):
                        raise ZipTraversalError()
                except Exception:
                    raise ZipTraversalError()

                # Check for suspicious patterns
                if ".." in entry.filename or entry.filename.startswith("/"):
                    raise ZipTraversalError()

            # Safe to extract
            zf.extractall(str(extract_dir))
            logger.info(f"ZIP extracted: {len(entries)} entries to {extract_dir}")

    @classmethod
    def _find_shp_file(cls, extract_dir: Path) -> Path:
        """Find the .shp file within the extracted directory."""
        shp_files = list(extract_dir.rglob("*.shp"))

        if not shp_files:
            raise InvalidShapefileError(
                "No .shp file found in the ZIP archive",
                missing_files=[".shp"],
            )

        if len(shp_files) > 1:
            logger.warning(
                f"Multiple .shp files found ({len(shp_files)}), using first: {shp_files[0].name}"
            )

        return shp_files[0]

    @classmethod
    def _verify_companions(cls, shp_path: Path) -> None:
        """
        Verify that required companion files exist alongside the .shp file.

        Required companions: .shx (spatial index), .dbf (attributes)
        """
        stem = shp_path.stem
        parent = shp_path.parent
        missing = []

        for ext in [".shx", ".dbf"]:
            # Check both cases
            companion = parent / f"{stem}{ext}"
            companion_upper = parent / f"{stem}{ext.upper()}"
            if not companion.exists() and not companion_upper.exists():
                missing.append(ext)

        if missing:
            raise InvalidShapefileError(
                f"Shapefile is missing required companion files: {', '.join(missing)}",
                missing_files=missing,
            )

    @classmethod
    def _detect_crs(cls, shp_path: Path) -> Optional[CRS]:
        """
        Detect CRS from the .prj companion file.

        The .prj file contains a WKT (Well-Known Text) representation
        of the Coordinate Reference System.
        """
        prj_path = shp_path.with_suffix(".prj")
        prj_path_upper = shp_path.with_suffix(".PRJ")

        actual_path = None
        if prj_path.exists():
            actual_path = prj_path
        elif prj_path_upper.exists():
            actual_path = prj_path_upper

        if actual_path is None:
            logger.warning("No .prj file found; CRS is unknown")
            return None

        try:
            prj_content = actual_path.read_text(encoding="utf-8").strip()
            crs = CRSResolver.detect_crs_from_prj(prj_content)
            if crs:
                logger.info(f"CRS detected from .prj: {crs.to_epsg() or crs.name}")
            else:
                logger.warning("Could not parse .prj file content")
            return crs
        except Exception as e:
            logger.warning(f"Error reading .prj file: {e}")
            return None
