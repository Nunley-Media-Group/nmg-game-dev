"""Desktop/Mobile variant path helpers and cross-reference guard.

Implements the split-variant asset convention from ``steering/structure.md``
§ split-variant asset convention::

    Content/<Category>/<Name>/Desktop/   — full-quality variant
    Content/<Category>/<Name>/Mobile/    — optimised variant

The ``assert_no_cross_reference`` guard checks that a variant's sidecar contains no paths that
leak across the variant boundary (e.g. a mobile sidecar referencing a Desktop/ path).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from nmg_game_dev.pipeline.errors import PipelineError


def desktop_path(consumer_content_root: Path, category: str, name: str) -> Path:
    """Return the Desktop variant directory for ``category`` and ``name``.

    The path is ``<consumer_content_root>/Content/<Category>/<Name>/Desktop/``.

    Args:
        consumer_content_root: The consumer project root (the directory that contains
            ``Content/``).
        category: Content category, e.g. ``Props``.
        name: Asset name, e.g. ``Crate``.

    Returns:
        A ``pathlib.Path`` to the Desktop variant directory.
    """
    return consumer_content_root / "Content" / category / name / "Desktop"


def mobile_path(consumer_content_root: Path, category: str, name: str) -> Path:
    """Return the Mobile variant directory for ``category`` and ``name``.

    The path is ``<consumer_content_root>/Content/<Category>/<Name>/Mobile/``.

    Args:
        consumer_content_root: The consumer project root (the directory that contains
            ``Content/``).
        category: Content category, e.g. ``Props``.
        name: Asset name, e.g. ``Crate``.

    Returns:
        A ``pathlib.Path`` to the Mobile variant directory.
    """
    return consumer_content_root / "Content" / category / name / "Mobile"


def assert_no_cross_reference(sidecar: Mapping[str, object] | None) -> None:
    """Raise ``PipelineError`` if a variant sidecar contains cross-variant path references.

    Inspects the string values of ``sidecar`` for paths that cross the Desktop/Mobile boundary:

    - A value containing ``"/Desktop/"`` in a mobile sidecar (``"variant": "mobile"``) references
      a Desktop path from the mobile side.
    - A value containing ``"/Mobile/"`` in a desktop sidecar (``"variant": "desktop"``) references
      a Mobile path from the desktop side.

    Args:
        sidecar: The variant sidecar mapping.  ``None`` and a non-string ``variant`` are not
            checked.

    Raises:
        PipelineError: With code ``variants.cross_reference`` when a cross-variant path is found.
    """
    if sidecar is None:
        return

    variant = sidecar.get("variant", "")
    if not isinstance(variant, str):
        return

    violations: list[str] = []
    for value in sidecar.values():
        if not isinstance(value, str):
            continue
        if variant == "mobile" and "/Desktop/" in value:
            violations.append(f"Mobile artifact references Desktop path: {value!r}")
        elif variant == "desktop" and "/Mobile/" in value:
            violations.append(f"Desktop artifact references Mobile path: {value!r}")

    if violations:
        raise PipelineError(
            code="variants.cross_reference",
            message=(
                f"Variant artifact contains cross-variant path references: {'; '.join(violations)}"
            ),
            remediation=(
                "Ensure the variants step writes Desktop assets only under "
                "Content/<Category>/<Name>/Desktop/ and Mobile assets only under "
                "Content/<Category>/<Name>/Mobile/.  Never reference paths from the "
                "opposite variant directory."
            ),
            stage="variants",
        )
