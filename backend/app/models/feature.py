"""
GeoMeasureX - Feature Model

Stores individual geometry features extracted from uploaded geospatial files.
Each feature includes its geometry (as GeoJSON), properties, validation status,
and links to its parent FileRecord and child Measurement.
"""

import uuid
from typing import Optional

from sqlalchemy import String, Integer, Boolean, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Feature(Base):
    """
    Represents a single geometry feature within an uploaded file.

    Stores the extracted geometry as GeoJSON, original properties/attributes,
    validation state, and repair tracking information.
    """

    __tablename__ = "features"

    # ── Identity ─────────────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("file_records.id", ondelete="CASCADE"), nullable=False
    )
    feature_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Geometry ─────────────────────────────────────────────────
    geometry_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    geometry_geojson: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bbox: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string [minx, miny, maxx, maxy]

    # ── Properties (from shapefile/KML attributes) ───────────────
    properties: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # ── CRS ──────────────────────────────────────────────────────
    source_crs: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # ── Validation ───────────────────────────────────────────────
    is_valid: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    validity_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_empty: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # ── Repair Tracking ──────────────────────────────────────────
    repair_attempted: Mapped[bool] = mapped_column(Boolean, default=False)
    repair_successful: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # ── Measurement Status ───────────────────────────────────────
    measurement_status: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )  # MEASURED, NOT_APPLICABLE, UNSUPPORTED, SKIPPED, FAILED

    # ── Relationships ────────────────────────────────────────────
    file_record: Mapped["FileRecord"] = relationship(
        "FileRecord", back_populates="features"
    )
    measurement: Mapped[Optional["Measurement"]] = relationship(
        "Measurement", back_populates="feature", cascade="all, delete-orphan", uselist=False
    )

    def __repr__(self) -> str:
        return (
            f"<Feature(id={self.id}, index={self.feature_index}, "
            f"type={self.geometry_type}, valid={self.is_valid})>"
        )
