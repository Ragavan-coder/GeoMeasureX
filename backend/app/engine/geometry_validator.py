"""
GeoMeasureX - Geometry Validator

Validates individual geometries, attempts safe repairs using Shapely's
make_valid, and tracks the full validation lifecycle (original validity,
repair attempt, repair outcome).

Design Decision:
    - Never silently alters geometry. Every repair is tracked and reported.
    - Invalid geometries that can't be repaired are flagged, not discarded.
    - One bad feature never crashes the entire file processing.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity, make_valid
from shapely import is_valid_reason

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Complete validation result for a single geometry."""

    original_valid: bool
    validity_reason: Optional[str] = None
    is_empty: bool = False
    is_null: bool = False
    repair_attempted: bool = False
    repair_successful: Optional[bool] = None
    final_geometry: Optional[BaseGeometry] = None
    geometry_used: str = "ORIGINAL"  # ORIGINAL, REPAIRED, SKIPPED

    @property
    def usable(self) -> bool:
        """Whether the geometry can be used for measurement."""
        if self.is_null or self.is_empty:
            return False
        if self.geometry_used == "SKIPPED":
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "original_valid": self.original_valid,
            "validity_reason": self.validity_reason,
            "is_empty": self.is_empty,
            "is_null": self.is_null,
            "repair_attempted": self.repair_attempted,
            "repair_successful": self.repair_successful,
            "geometry_used": self.geometry_used,
        }


class GeometryValidator:
    """
    Validates and optionally repairs geometries.

    Validation checks:
        1. Null geometry (None)
        2. Empty geometry (no coordinates)
        3. Shapely is_valid (OGC validity: no self-intersections, proper rings, etc.)

    Repair:
        - Uses Shapely's make_valid() which applies OGC-compliant fixes
        - make_valid may return a different geometry type (e.g., MultiPolygon from Polygon)
        - All repairs are tracked and reported
    """

    @classmethod
    def validate(
        cls,
        geometry: Optional[BaseGeometry],
        attempt_repair: bool = True,
    ) -> ValidationResult:
        """
        Validate a geometry and optionally attempt repair if invalid.

        Args:
            geometry: The Shapely geometry to validate (may be None).
            attempt_repair: Whether to attempt make_valid on invalid geometries.

        Returns:
            ValidationResult with full lifecycle tracking.
        """
        # Check for null geometry
        if geometry is None:
            logger.debug("Null geometry encountered")
            return ValidationResult(
                original_valid=False,
                validity_reason="Null geometry",
                is_null=True,
                geometry_used="SKIPPED",
            )

        # Check for empty geometry
        if geometry.is_empty:
            logger.debug("Empty geometry encountered")
            return ValidationResult(
                original_valid=False,
                validity_reason="Empty geometry",
                is_empty=True,
                final_geometry=geometry,
                geometry_used="SKIPPED",
            )

        # Check OGC validity
        is_valid = geometry.is_valid
        reason = None if is_valid else explain_validity(geometry)

        if is_valid:
            return ValidationResult(
                original_valid=True,
                final_geometry=geometry,
                geometry_used="ORIGINAL",
            )

        # Geometry is invalid — attempt repair if requested
        logger.info(
            "Invalid geometry detected",
            extra={"reason": reason},
        )

        if not attempt_repair:
            return ValidationResult(
                original_valid=False,
                validity_reason=reason,
                final_geometry=geometry,
                geometry_used="ORIGINAL",
            )

        return cls._attempt_repair(geometry, reason)

    @classmethod
    def _attempt_repair(
        cls,
        geometry: BaseGeometry,
        original_reason: str,
    ) -> ValidationResult:
        """
        Attempt to repair an invalid geometry using Shapely's make_valid.

        make_valid implements the OGC approach:
            - Fixes self-intersections by splitting/merging
            - Fixes improper ring orientations
            - May change geometry type (Polygon → MultiPolygon)
        """
        try:
            repaired = make_valid(geometry)
            repair_ok = repaired.is_valid and not repaired.is_empty

            if repair_ok:
                logger.info("Geometry successfully repaired")
            else:
                logger.warning(
                    "Geometry repair attempted but result still invalid",
                    extra={"post_repair_valid": repaired.is_valid},
                )

            return ValidationResult(
                original_valid=False,
                validity_reason=original_reason,
                repair_attempted=True,
                repair_successful=repair_ok,
                final_geometry=repaired if repair_ok else geometry,
                geometry_used="REPAIRED" if repair_ok else "ORIGINAL",
            )
        except Exception as e:
            logger.error(f"Geometry repair failed with exception: {e}")
            return ValidationResult(
                original_valid=False,
                validity_reason=original_reason,
                repair_attempted=True,
                repair_successful=False,
                final_geometry=geometry,
                geometry_used="ORIGINAL",
            )

    @classmethod
    def validate_batch(
        cls,
        geometries: list[Optional[BaseGeometry]],
        attempt_repair: bool = True,
    ) -> list[ValidationResult]:
        """Validate a batch of geometries."""
        return [cls.validate(g, attempt_repair) for g in geometries]
