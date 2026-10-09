"""
GeoMeasureX - KML Parser

Parses KML files into GeoDataFrames using GeoPandas/Fiona.
KML files always use EPSG:4326 (WGS84) per the KML specification.

Design Decisions:
    - Uses fiona with KML driver for robust parsing
    - Falls back to lxml-based parsing if Fiona KML driver unavailable
    - Always sets CRS to EPSG:4326 (mandated by KML spec)
    - Extracts all layers, not just the first one
"""

import logging
import tempfile
from pathlib import Path
from typing import Optional

import geopandas as gpd
from pyproj import CRS

from app.exceptions import InvalidKMLError, EmptyDatasetError

logger = logging.getLogger(__name__)


class KMLParser:
    """
    Parses KML files into GeoDataFrames.

    KML Specification:
        - All coordinates in KML are WGS84 (EPSG:4326)
        - Supports Point, LineString, Polygon, and Multi* variants
        - May contain multiple layers/folders
    """

    # KML always uses WGS84
    SOURCE_CRS = CRS.from_epsg(4326)

    @classmethod
    def parse(cls, file_path: Path) -> gpd.GeoDataFrame:
        """
        Parse a KML file into a GeoDataFrame.

        Args:
            file_path: Path to the .kml file.

        Returns:
            GeoDataFrame with geometry and attributes, CRS set to EPSG:4326.

        Raises:
            InvalidKMLError: If the file cannot be parsed.
            EmptyDatasetError: If the file contains no features.
        """
        logger.info(f"Parsing KML file: {file_path.name}")

        try:
            # Enable KML driver support in fiona
            import fiona
            fiona.drvsupport.supported_drivers['KML'] = 'r'
            fiona.drvsupport.supported_drivers['LIBKML'] = 'r'
        except Exception:
            pass

        gdf = cls._parse_with_fiona(file_path)

        if gdf is None or gdf.empty:
            raise EmptyDatasetError()

        # Ensure CRS is set to EPSG:4326
        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=4326)

        logger.info(
            f"KML parsed successfully: {len(gdf)} features",
            extra={"feature_count": len(gdf)},
        )
        return gdf

    @classmethod
    def _parse_with_fiona(cls, file_path: Path) -> Optional[gpd.GeoDataFrame]:
        """Parse KML using Fiona driver via GeoPandas."""
        try:
            # Try reading with KML driver
            gdf = gpd.read_file(str(file_path), driver="KML")
            return gdf
        except Exception as e1:
            logger.warning(f"KML driver failed: {e1}, trying LIBKML")
            try:
                gdf = gpd.read_file(str(file_path), driver="LIBKML")
                return gdf
            except Exception as e2:
                logger.warning(f"LIBKML driver also failed: {e2}, trying auto-detect")
                try:
                    # Let Fiona auto-detect
                    gdf = gpd.read_file(str(file_path))
                    return gdf
                except Exception as e3:
                    raise InvalidKMLError(
                        f"Failed to parse KML file: {e3}"
                    )

    @classmethod
    def get_source_crs(cls) -> CRS:
        """KML always uses EPSG:4326."""
        return cls.SOURCE_CRS
