"""Quality gate implementations — budget checks and manifest validation.

Pure-logic module: no MCP calls, no filesystem writes.  Every function is
deterministic — given the same sidecar and budget, it always returns the same
report.  The finalize pipeline (#69) gates its reports with ``quality.contract``;
these budget and manifest checks take a plain variant sidecar mapping.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel


class MobileBudget(BaseModel):
    """Poly and texture budget thresholds for the mobile variant.

    Attributes:
        poly_budget: Maximum allowed polygon count for the mobile variant.
        texture_byte_budget: Maximum allowed total texture size in bytes for
            the mobile variant.
    """

    poly_budget: int
    texture_byte_budget: int


class BudgetReport(BaseModel):
    """Result of a mobile budget check against a single artifact.

    Attributes:
        variant: Which variant was checked.
        poly_count: Actual polygon count read from the artifact sidecar.
        texture_bytes: Actual total texture size read from the artifact sidecar.
        poly_budget: The budget that was applied, or ``None`` if unchecked.
        texture_budget: The texture budget that was applied, or ``None`` if unchecked.
        passed: ``True`` when all checked metrics are within budget.
        reasons: Human-readable failure descriptions; empty when ``passed`` is ``True``.
    """

    variant: Literal["desktop", "mobile"]
    poly_count: int
    texture_bytes: int
    poly_budget: int | None
    texture_budget: int | None
    passed: bool
    reasons: list[str]


class ManifestReport(BaseModel):
    """Result of manifest-prep field validation against a single artifact.

    Attributes:
        passed: ``True`` when all required manifest fields are present and
            well-typed in the artifact sidecar.
        reasons: Human-readable failure descriptions; empty when ``passed`` is ``True``.
    """

    passed: bool
    reasons: list[str]


_REQUIRED_MANIFEST_FIELDS: dict[str, type] = {
    "desktop_path": str,
    "mobile_path": str,
    "poly_count_desktop": int,
    "poly_count_mobile": int,
    "texture_bytes_desktop": int,
    "texture_bytes_mobile": int,
}


def _as_int(value: object, default: int = 0) -> int:
    # bool is a subclass of int; guard explicitly so True/False don't coerce to 1/0.
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    return default


def check_mobile_budget(
    sidecar: Mapping[str, object] | None,
    budget: MobileBudget,
) -> BudgetReport:
    """Check the mobile variant sidecar against poly and texture budgets.

    Reads ``poly_count_mobile`` and ``texture_bytes_mobile`` from ``sidecar``.  Missing or
    non-integer fields are treated as zero — a missing value typically surfaces as a manifest
    check failure downstream.
    """
    sidecar = sidecar or {}
    poly_count = _as_int(sidecar.get("poly_count_mobile"))
    texture_bytes = _as_int(sidecar.get("texture_bytes_mobile"))

    reasons: list[str] = []

    if poly_count > budget.poly_budget:
        reasons.append(
            f"Mobile poly count {poly_count:,} exceeds budget {budget.poly_budget:,} "
            f"(overage: {poly_count - budget.poly_budget:,} polygons). "
            f"Reduce mesh complexity or apply additional decimation."
        )

    if texture_bytes > budget.texture_byte_budget:
        reasons.append(
            f"Mobile texture size {texture_bytes:,} bytes exceeds budget "
            f"{budget.texture_byte_budget:,} bytes "
            f"(overage: {texture_bytes - budget.texture_byte_budget:,} bytes). "
            f"Reduce texture resolution or compress textures."
        )

    return BudgetReport(
        variant="mobile",
        poly_count=poly_count,
        texture_bytes=texture_bytes,
        poly_budget=budget.poly_budget,
        texture_budget=budget.texture_byte_budget,
        passed=not reasons,
        reasons=reasons,
    )


def check_manifest(sidecar: Mapping[str, object] | None) -> ManifestReport:
    """Validate that the variant sidecar contains all required manifest fields.

    Checks each field in ``_REQUIRED_MANIFEST_FIELDS`` for presence and correct type. Type
    coercion is not attempted — the value must already be an instance of the expected type.
    """
    sidecar = sidecar or {}
    reasons: list[str] = []

    for field_name, expected_type in _REQUIRED_MANIFEST_FIELDS.items():
        value = sidecar.get(field_name)
        if value is None:
            reasons.append(
                f"Required manifest field {field_name!r} is missing from the "
                f"variants artifact sidecar."
            )
        elif not isinstance(value, expected_type):
            reasons.append(
                f"Manifest field {field_name!r} has type {type(value).__name__!r} "
                f"but expected {expected_type.__name__!r}."
            )

    return ManifestReport(passed=not reasons, reasons=reasons)
