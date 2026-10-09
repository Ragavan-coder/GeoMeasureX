"""
GeoMeasureX - CRS Resolver

Intelligently selects the appropriate projected Coordinate Reference System
for accurate physical measurements. Handles UTM zone selection based on
geometry centroid, hemisphere detection, and fallback strategies for
datasets spanning multiple zones.

Key Design Decisions:
    - UTM is preferred for datasets within a single 6° longitude band
    - Lambert Azimuthal Equal-Area is used for wide-spanning datasets
    - The CRS decision is deterministic and fully explainable
    - Never hard-codes a single CRS for all data (e.g., EPSG:3857)
"""

import math
import logging
from dataclasses import dataclass
from typing import Optional

from pyproj import CRS
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

logger = logging.getLogger(__name__)


@dataclass
class CRSResolution:
    """Result of CRS resolution with full traceability."""

    source_crs: CRS
    measurement_crs: CRS
    strategy: str
    source_epsg: Optional[str] = None
    measurement_epsg: Optional[str] = None
    utm_zone: Optional[int] = None
    hemisphere: Optional[str] = None
    centroid_lon: Optional[float] = None
    centroid_lat: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "source_crs": self.source_epsg or str(self.source_crs),
            "measurement_crs": self.measurement_epsg or str(self.measurement_crs),
            "crs_strategy": self.strategy,
            "utm_zone": self.utm_zone,
            "hemisphere": self.hemisphere,
            "centroid_lon": self.centroid_lon,
            "centroid_lat": self.centroid_lat,
        }


class CRSResolver:
    """
    Resolves the appropriate measurement CRS for a given dataset.

    Strategy:
        1. If the source CRS is already projected (units=meters), use it directly.
        2. If geographic (lat/lon), determine the dataset centroid.
        3. If the dataset spans ≤ 6° longitude, use the appropriate UTM zone.
        4. If wider, fall back to Lambert Azimuthal Equal-Area centered on the centroid.

    UTM Zone Formula:
        zone_number = floor((longitude + 180) / 6) + 1
        Northern Hemisphere: EPSG = 32600 + zone_number
        Southern Hemisphere: EPSG = 32700 + zone_number
    """

    # Maximum longitude span (degrees) before falling back from UTM
    MAX_UTM_SPAN_DEGREES: float = 6.0

    @classmethod
    def resolve(
        cls,
        source_crs: CRS,
        geometry_bounds: tuple[float, float, float, float],
    ) -> CRSResolution:
        """
        Resolve the measurement CRS for the given source CRS and dataset bounds.

        Args:
            source_crs: The detected source CRS of the dataset.
            geometry_bounds: (minx, miny, maxx, maxy) bounding box in source CRS.

        Returns:
            CRSResolution with source, measurement CRS, and strategy explanation.
        """
        source_epsg = cls._get_epsg_string(source_crs)

        # If already projected with metric units, use directly
        if source_crs.is_projected:
            axis_info = source_crs.axis_info
            units = [a.unit_name for a in axis_info] if axis_info else []
            if any("metre" in u.lower() or "meter" in u.lower() for u in units):
                logger.info(
                    "Source CRS is projected with metric units, using directly",
                    extra={"source_crs": source_epsg},
                )
                return CRSResolution(
                    source_crs=source_crs,
                    measurement_crs=source_crs,
                    strategy="SOURCE_PROJECTED_METRIC",
                    source_epsg=source_epsg,
                    measurement_epsg=source_epsg,
                )

        # Geographic CRS — need to select a projected CRS
        minx, miny, maxx, maxy = geometry_bounds

        # If source is projected but non-metric, transform bounds to WGS84 for analysis
        if source_crs.is_projected:
            from pyproj import Transformer
            transformer = Transformer.from_crs(source_crs, CRS.from_epsg(4326), always_xy=True)
            minx, miny = transformer.transform(minx, miny)
            maxx, maxy = transformer.transform(maxx, maxy)

        centroid_lon = (minx + maxx) / 2.0
        centroid_lat = (miny + maxy) / 2.0
        lon_span = abs(maxx - minx)

        logger.info(
            "Resolving measurement CRS",
            extra={
                "centroid_lon": centroid_lon,
                "centroid_lat": centroid_lat,
                "lon_span": lon_span,
            },
        )

        if lon_span <= cls.MAX_UTM_SPAN_DEGREES:
            return cls._select_utm(source_crs, source_epsg, centroid_lon, centroid_lat)
        else:
            return cls._select_equal_area(
                source_crs, source_epsg, centroid_lon, centroid_lat, lon_span
            )

    @classmethod
    def _select_utm(
        cls,
        source_crs: CRS,
        source_epsg: str,
        centroid_lon: float,
        centroid_lat: float,
    ) -> CRSResolution:
        """
        Select the appropriate UTM zone based on centroid coordinates.

        Formula:
            zone_number = floor((longitude + 180) / 6) + 1
            EPSG = 32600 + zone (Northern) or 32700 + zone (Southern)
        """
        zone_number = int(math.floor((centroid_lon + 180) / 6)) + 1
        zone_number = max(1, min(60, zone_number))  # Clamp to valid range

        hemisphere = "N" if centroid_lat >= 0 else "S"
        epsg_code = (32600 if hemisphere == "N" else 32700) + zone_number

        measurement_crs = CRS.from_epsg(epsg_code)
        measurement_epsg = f"EPSG:{epsg_code}"
        strategy = f"UTM_ZONE_{zone_number}{hemisphere}"

        logger.info(
            "Selected UTM zone",
            extra={
                "zone": zone_number,
                "hemisphere": hemisphere,
                "epsg": epsg_code,
            },
        )

        return CRSResolution(
            source_crs=source_crs,
            measurement_crs=measurement_crs,
            strategy=strategy,
            source_epsg=source_epsg,
            measurement_epsg=measurement_epsg,
            utm_zone=zone_number,
            hemisphere=hemisphere,
            centroid_lon=centroid_lon,
            centroid_lat=centroid_lat,
        )

    @classmethod
    def _select_equal_area(
        cls,
        source_crs: CRS,
        source_epsg: str,
        centroid_lon: float,
        centroid_lat: float,
        lon_span: float,
    ) -> CRSResolution:
        """
        Fall back to Lambert Azimuthal Equal-Area projection centered on
        the dataset centroid. Used when the dataset spans multiple UTM zones.

        This projection preserves area measurements (critical for our use case)
        and is centered on the dataset for minimal distortion.
        """
        proj4 = (
            f"+proj=laea +lat_0={centroid_lat} +lon_0={centroid_lon} "
            f"+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
        )
        measurement_crs = CRS.from_proj4(proj4)
        strategy = f"LAMBERT_AZIMUTHAL_EQUAL_AREA (dataset spans {lon_span:.1f}° longitude)"

        logger.info(
            "Selected Lambert Azimuthal Equal-Area (dataset too wide for single UTM zone)",
            extra={"lon_span": lon_span, "centroid": (centroid_lon, centroid_lat)},
        )

        return CRSResolution(
            source_crs=source_crs,
            measurement_crs=measurement_crs,
            strategy=strategy,
            source_epsg=source_epsg,
            measurement_epsg=f"Custom LAEA (centered {centroid_lat:.2f}°, {centroid_lon:.2f}°)",
            centroid_lon=centroid_lon,
            centroid_lat=centroid_lat,
        )

    @staticmethod
    def _get_epsg_string(crs: CRS) -> str:
        """Extract EPSG string from CRS, or return WKT description."""
        try:
            epsg = crs.to_epsg()
            if epsg:
                return f"EPSG:{epsg}"
        except Exception:
            pass
        return str(crs.name) if crs.name else "UNKNOWN"

    @staticmethod
    def detect_crs_from_prj(prj_content: str) -> Optional[CRS]:
        """Parse a .prj file's WKT content to determine CRS."""
        try:
            return CRS.from_wkt(prj_content)
        except Exception:
            try:
                return CRS.from_user_input(prj_content)
            except Exception:
                return None
