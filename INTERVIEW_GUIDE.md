# GeoMeasureX - Interview Guide

## 60-Second Elevator Pitch
"GeoMeasureX is a production-ready geospatial API and dashboard that securely processes KML and Shapefile uploads to extract highly accurate physical measurements. Instead of naively measuring on geographic coordinates which produces meaningless results, it features a smart CRS engine that dynamically selects the optimal metric projection based on the dataset's geographic footprint. It also includes an automated QA layer to repair invalid geometries and flag data anomalies, exposed via a fast FastAPI backend and a React dashboard."

## 2-Minute Architecture Explanation
"When a file is uploaded, it passes through 5 distinct pipeline stages. 
1. **Security Layer**: We validate the MIME type, enforce size limits, and for ZIPs, scan for zip-bombs and path traversal attacks before safe extraction.
2. **Parser**: We parse the file into a GeoDataFrame using GeoPandas, enforcing EPSG:4326 for KML and reading the `.prj` file for Shapefiles.
3. **Geometry QA**: Every geometry is validated against OGC rules. If invalid (like a self-intersection), we attempt to fix it using Shapely's `make_valid`, tracking whether the repair succeeded.
4. **CRS Intelligence**: We calculate the dataset's centroid, determine the appropriate UTM zone using `floor((lon+180)/6)+1`, and project the coordinates into meters. If it spans multiple zones, we fall back to a Lambert Azimuthal Equal Area projection.
5. **Measurement & Quality**: We calculate exact areas using the Shoelace formula on the projected coordinates. A Quality Engine then scans for zero-area, tiny, or impossibly large polygons and generates structured warnings. The results are persisted to SQLite and displayed on a React-Leaflet frontend."

## Key Design Decisions & Q&A

**1. Why FastAPI?**
It provides built-in Pydantic validation for our complex JSON measurement schemas, automatic OpenAPI documentation (critical for API handoffs), and high performance through Starlette. 

**2. Why GeoPandas & Shapely?**
GeoPandas gives us vectorized operations which are much faster for large files than looping in pure Python. Shapely provides bindings to the GEOS C++ library for robust, OGC-compliant geometry operations like `make_valid` and `.area`.

**3. Why not calculate area directly on EPSG:4326?**
EPSG:4326 coordinates are in degrees. Calculating area yields "square degrees," which is physically meaningless because the distance between longitudes shrinks as you move from the equator to the poles.

**4. How do you handle a dataset that crosses two UTM zones?**
If the dataset's bounding box spans more than 6 degrees of longitude, projecting into a single UTM zone would introduce unacceptable distortion at the edges. In that case, our `CRSResolver` automatically falls back to a custom Lambert Azimuthal Equal Area (LAEA) projection centered exactly on the dataset's centroid.

**5. How do you handle one invalid polygon crashing the whole job?**
We isolate geometry processing. If a polygon is invalid (e.g., ring self-intersection), our `GeometryValidator` attempts a repair. If the repair fails, that specific feature's measurement status is marked as `SKIPPED` and a quality warning is attached, but the rest of the dataset is processed successfully.

**6. What's the biggest challenge with Shapefiles?**
They are actually a collection of at least 3-4 files (.shp, .shx, .dbf, .prj) bundled in a ZIP. The challenge is safely extracting them without falling victim to path traversal attacks (e.g., `../../../etc/passwd` inside the zip header), ensuring all companion files exist, and correctly parsing the WKT inside the `.prj` file.

**7. How would you scale this for massive files?**
Currently, processing is synchronous. I would introduce Celery or RQ workers. FastAPI would return a `202 Accepted` with a Job ID. The worker would process the file asynchronously, upload results to S3, and update the database status to `COMPLETED`. The React frontend would poll or use WebSockets to listen for completion.

**8. How do you test geospatial accuracy?**
Floating-point equality is dangerous with geospatial math. We use deterministic test fixtures (like a known 100x100m polygon in UTM) and assert that the calculated area matches the expected area within a strict tolerance limit (e.g., `< 0.1%` error).
