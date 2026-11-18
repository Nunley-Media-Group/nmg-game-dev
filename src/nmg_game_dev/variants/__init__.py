"""Desktop/Mobile variant path helpers and cross-reference guard.

Implements the split-variant asset convention (``docs/asset-contract.md``) inside the consumer's
Godot project::

    game/assets/<Category>/<Name>/Desktop/   — full-quality variant
    game/assets/<Category>/<Name>/Mobile/    — optimised variant

The ``assert_no_cross_reference`` guard checks that a variant's sidecar contains no paths that
leak across the variant boundary (e.g. a mobile sidecar referencing a Desktop/ path).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from nmg_game_dev.pipeline.errors import PipelineError

ASSETS_DIR = Path("game") / "assets"


def desktop_path(consumer_root: Path, category: str, name: str) -> Path:
    """Return the Desktop variant directory for ``category`` and ``name``.

    The path is ``<consumer_root>/game/assets/<Category>/<Name>/Desktop/``.

    Args:
        consumer_root: The consumer project root (the directory that contains ``game/``).
        category: Asset category, e.g. ``Props``.
        name: Asset name, e.g. ``Crate``.

    Returns:
        A ``pathlib.Path`` to the Desktop variant directory.
    """
    return consumer_root / ASSETS_DIR / category / name / "Desktop"


def mobile_path(consumer_root: Path, category: str, name: str) -> Path:
    """Return the Mobile variant directory for ``category`` and ``name``.

    The path is ``<consumer_root>/game/assets/<Category>/<Name>/Mobile/``.

    Args:
        consumer_root: The consumer project root (the directory that contains ``game/``).
        category: Asset category, e.g. ``Props``.
        name: Asset name, e.g. ``Crate``.

    Returns:
        A ``pathlib.Path`` to the Mobile variant directory.
    """
    return consumer_root / ASSETS_DIR / category / name / "Mobile"


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
                "game/assets/<Category>/<Name>/Desktop/ and Mobile assets only under "
                "game/assets/<Category>/<Name>/Mobile/.  Never reference paths from the "
                "opposite variant directory."
            ),
            stage="variants",
        )
