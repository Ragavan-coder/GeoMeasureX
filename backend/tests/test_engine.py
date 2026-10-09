import pytest
from pyproj import CRS
from shapely.geometry import Polygon, LineString

from app.engine.crs_resolver import CRSResolver
from app.engine.measurement_engine import MeasurementEngine
from app.engine.quality_engine import QualityEngine

def test_utm_zone_selection_northern_hemisphere():
    """Test UTM zone math for Northern Hemisphere (Hyderabad, India)."""
    # 78.5 E, 17.5 N -> Zone 44N (EPSG:32644)
    # zone = floor((78.5 + 180) / 6) + 1 = 44
    res = CRSResolver._select_utm(CRS.from_epsg(4326), "EPSG:4326", 78.5, 17.5)
    
    assert res.utm_zone == 44
    assert res.hemisphere == "N"
    assert "32644" in res.measurement_epsg


def test_utm_zone_selection_southern_hemisphere():
    """Test UTM zone math for Southern Hemisphere (Sydney, Australia)."""
    # 151.2 E, -33.8 S -> Zone 56S (EPSG:32756)
    res = CRSResolver._select_utm(CRS.from_epsg(4326), "EPSG:4326", 151.2, -33.8)
    
    assert res.utm_zone == 56
    assert res.hemisphere == "S"
    assert "32756" in res.measurement_epsg


def test_measurement_engine_polygon_area_accuracy():
    """
    Test polygon area measurement accuracy using a known projected square.
    A 100m x 100m square should equal exactly 10,000 square meters.
    """
    # Create a 100x100m square directly in UTM (meters)
    # Coordinates: (0,0) to (100,100)
    square = Polygon([(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)])
    
    # We bypass the dataframe logic to test the core measurement method
    engine = MeasurementEngine()
    
    class DummyFeatureMeasurement:
        pass
    
    fm = DummyFeatureMeasurement()
    fm.warnings = []
    
    result = engine._measure_polygon(fm, square, 1, False)
    
    # Assert exact or highly precise area
    assert abs(result.area_m2 - 10_000.0) < 0.01  # Tolerance of 0.01 sq meters
    assert abs(result.area_hectares - 1.0) < 0.0001


def test_quality_engine_zero_area():
    """Test that zero area polygons trigger a WARNING."""
    warnings = QualityEngine.check_polygon(
        area_m2=0.005,  # Below 0.01 threshold
        feature_index=1,
        is_valid=True,
        was_repaired=False
    )
    
    assert len(warnings) == 1
    assert warnings[0].code == "ZERO_AREA_GEOMETRY"
    assert warnings[0].severity == "WARNING"


def test_quality_engine_huge_polygon():
    """Test that impossibly large polygons trigger a WARNING."""
    warnings = QualityEngine.check_polygon(
        area_m2=2_000_000_000_000,  # 2 Million km^2
        feature_index=2,
        is_valid=True,
        was_repaired=False
    )
    
    assert len(warnings) == 1
    assert warnings[0].code == "EXTREMELY_LARGE_POLYGON"
    assert warnings[0].severity == "WARNING"
