# GeoMeasureX

## Intelligent Geospatial File Measurement & Validation API

GeoMeasureX is a production-grade geospatial processing engine built for accuracy, resilience, and security. It is not just an API; it is a full pipeline that parses, validates, repairs, and intelligently projects geospatial geometries to produce physically meaningful measurements.

### 🚀 Features

- **KML & Shapefile Support**: Process `.kml` and `.zip` Shapefile archives securely.
- **CRS Intelligence Engine**: Automatically detects source CRS and determines the optimal metric Coordinate Reference System (UTM or Lambert Azimuthal Equal Area) based on the dataset's geographic footprint.
- **True Physical Measurements**: Calculates area (m², hectares, km²) and length (m, km) using the Shoelace formula and Euclidean distance on projected coordinates. NEVER measures area on EPSG:4326.
- **Geometry QA & Repair**: Detects invalid geometries (e.g. self-intersections) and repairs them using OGC-compliant `make_valid` routines.
- **Quality Engine**: Threshold-based anomaly detection for zero-area polygons, tiny/huge features, missing CRS, and empty geometries.
- **Security First**: Prevents zip-bomb attacks, path traversal, and malicious payloads during extraction.
- **Professional UI**: A stunning dark-mode React dashboard with interactive Leaflet map visualization.

---

## 🏗 Architecture Pipeline

```text
             UPLOAD
                │
                ▼
       ┌─────────────────┐
       │ Security Layer  │ (Validate MIME, extension, size, path traversal)
       └────────┬────────┘
                ▼
       ┌─────────────────┐
       │ File Parser     │ (KML / Shapefile ZIP)
       └────────┬────────┘
                ▼
       ┌─────────────────┐
       │ Geometry QA     │ (is_valid, make_valid repair)
       └────────┬────────┘
                ▼
       ┌─────────────────┐
       │ CRS Intelligence│ (Detect source CRS → select optimal UTM/LAEA)
       └────────┬────────┘
                ▼
       ┌─────────────────┐
       │ Measurement     │ (Area / Length on projected metric coords)
       └────────┬────────┘
                ▼
       ┌─────────────────┐
       │ Quality Engine  │ (Generate structured warnings)
       └────────┬────────┘
                ▼
       ┌─────────────────┐
       │ Results + Map   │ (Persist to SQLite, return GeoJSON)
       └─────────────────┘
```

---

## 🛠 Technology Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn, SQLAlchemy
- **Geospatial Engine**: GeoPandas, Shapely, PyProj, Fiona
- **Frontend**: React, TypeScript, Vite, Tailwind CSS, React-Leaflet
- **Database**: SQLite (local) / PostgreSQL + PostGIS (production ready)

---

## 🏃 Running Locally

1. **Backend**:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # or .\venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
   API Docs available at: `http://localhost:8000/docs`

2. **Frontend**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Dashboard available at: `http://localhost:5173`

---

## 🧠 Design Decisions & Interview Notes

### Why not EPSG:4326 for measurements?
EPSG:4326 uses degrees. Calculating area in "square degrees" is physically meaningless and highly distorted depending on latitude. We always project to a metric system before measuring.

### How is UTM selection deterministic?
The engine calculates the centroid of the dataset's bounding box. 
Formula: `zone = floor((longitude + 180) / 6) + 1`. 
It then detects the hemisphere and assigns the correct EPSG code (326xx or 327xx). If the dataset spans more than 6° longitude, it gracefully falls back to a custom Lambert Azimuthal Equal Area projection centered on the dataset.

### Geometry Validation
Instead of crashing on one invalid polygon (like a self-intersection), the Geometry Validator runs Shapely's `make_valid()`, repairs it if possible, and flags it. If unrepairable, it skips measurement but still processes the rest of the file.

### Security
Uploaded archives are extracted to isolated temp directories. Every path within the ZIP is checked for absolute paths and `../` traversal patterns before extraction.

---
*For a deeper dive into architecture and interview Q&A, see `INTERVIEW_GUIDE.md`.*
