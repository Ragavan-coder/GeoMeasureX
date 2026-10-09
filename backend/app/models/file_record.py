"""
GeoMeasureX - FileRecord Model

Stores metadata about uploaded geospatial files and their processing status.
Designed for SQLite locally with PostgreSQL/PostGIS migration path.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, Float, Text, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class FileStatus(str, enum.Enum):
    """Processing lifecycle states."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FileType(str, enum.Enum):
    """Supported geospatial file types."""
    KML = "KML"
    SHAPEFILE = "SHAPEFILE"


class FileRecord(Base):
    """
    Represents an uploaded geospatial file and its processing results.

    Tracks the full lifecycle from upload through CRS detection,
    geometry processing, and measurement completion.
    """

    __tablename__ = "file_records"

    # ── Identity ─────────────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # ── CRS Information ──────────────────────────────────────────
    source_crs: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    measurement_crs: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    crs_strategy: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ── Processing ───────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20), default=FileStatus.PENDING.value, nullable=False
    )
    feature_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    processing_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── File metadata ────────────────────────────────────────────
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Timestamps ───────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ────────────────────────────────────────────
    features: Mapped[list["Feature"]] = relationship(
        "Feature", back_populates="file_record", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<FileRecord(id={self.id}, filename={self.filename}, status={self.status})>"
