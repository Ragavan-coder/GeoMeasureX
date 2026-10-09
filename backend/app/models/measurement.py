"""
GeoMeasureX - Measurement Model

Stores calculated measurements for each feature. Measurements are always
performed on properly projected coordinates (never on raw lat/lon).
"""

import uuid
from typing import Optional

from sqlalchemy import String, Float, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Measurement(Base):
    """
    Stores physical measurements calculated from a single geometry feature.

    Area values are only populated for Polygon/MultiPolygon geometries.
    Length values are only populated for LineString/MultiLineString geometries.
    All values are calculated from geometry transformed to a metric projected CRS.
    """

    __tablename__ = "measurements"

    # ── Identity ─────────────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    feature_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("features.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )

    # ── CRS used for measurement ─────────────────────────────────
    measurement_crs: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    crs_strategy: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ── Polygon Measurements ─────────────────────────────────────
    area_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    area_hectares: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    area_km2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── LineString Measurements ──────────────────────────────────
    length_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    length_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── Perimeter (for polygons) ─────────────────────────────────
    perimeter_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── Quality Warnings ─────────────────────────────────────────
    warnings: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # ── Relationship ─────────────────────────────────────────────
    feature: Mapped["Feature"] = relationship(
        "Feature", back_populates="measurement"
    )

    def __repr__(self) -> str:
        return (
            f"<Measurement(id={self.id}, area_m2={self.area_m2}, "
            f"length_m={self.length_m})>"
        )
