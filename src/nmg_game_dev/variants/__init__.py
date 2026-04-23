"""Desktop/Mobile variant path helpers and cross-reference guard.

Implements the split-variant asset convention from ``steering/structure.md``
§ split-variant asset convention::

    Content/<Category>/<Name>/Desktop/   — full-quality variant
    Content/<Category>/<Name>/Mobile/    — optimised variant

The ``assert_no_cross_reference`` guard checks that an artifact's sidecar
contains no paths that leak across the variant boundary (e.g. a mobile
sidecar referencing a Desktop/ path).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nmg_game_dev.pipeline.stages._base import StageArtifact

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.prompt import Prompt


def desktop_path(consumer_content_root: Path, prompt: Prompt) -> Path:
    """Return the Desktop variant directory for the given prompt.

    Per the split-variant asset convention, the path is::

        <consumer_content_root>/Content/<Category>/<Name>/Desktop/

    Args:
        consumer_content_root: Root of the consumer project's ``Content/``
            parent directory (i.e. the project root, not ``Content/`` itself).
        prompt: The validated asset-generation prompt.

    Returns:
        A ``pathlib.Path`` to the Desktop variant directory.
    """
    return consumer_content_root / "Content" / prompt.category / prompt.name / "Desktop"


def mobile_path(consumer_content_root: Path, prompt: Prompt) -> Path:
    """Return the Mobile variant directory for the given prompt.

    Per the split-variant asset convention, the path is::

        <consumer_content_root>/Content/<Category>/<Name>/Mobile/

    Args:
        consumer_content_root: Root of the consumer project's ``Content/``
            parent directory (i.e. the project root, not ``Content/`` itself).
        prompt: The validated asset-generation prompt.

    Returns:
        A ``pathlib.Path`` to the Mobile variant directory.
    """
    return consumer_content_root / "Content" / prompt.category / prompt.name / "Mobile"


def assert_no_cross_reference(artifact: StageArtifact) -> None:
    """Raise ``PipelineError`` if the artifact contains cross-variant path references.

    Inspects string values in ``artifact.sidecar`` for paths that cross the
    Desktop/Mobile boundary:

    - A sidecar value containing ``"/Desktop/"`` when the variant is ``"mobile"``
      indicates a mobile artifact referencing a desktop path.
    - A sidecar value containing ``"/Mobile/"`` when the variant is ``"desktop"``
      indicates a desktop artifact referencing a mobile path.

    Args:
        artifact: The ``StageArtifact`` produced by the variants stage.

    Raises:
        PipelineError: With code ``"variants.cross_reference"`` when a
            cross-variant path is detected.
    """
    if artifact.sidecar is None:
        return

    variant = artifact.sidecar.get("variant", "")
    if not isinstance(variant, str):
        return

    def _check_value(val: object) -> str | None:
        """Return a violation description if val is a cross-variant string path."""
        if not isinstance(val, str):
            return None
        if variant == "mobile" and "/Desktop/" in val:
            return f"Mobile artifact references Desktop path: {val!r}"
        if variant == "desktop" and "/Mobile/" in val:
            return f"Desktop artifact references Mobile path: {val!r}"
        return None

    violations: list[str] = []
    for _key, value in artifact.sidecar.items():
        msg = _check_value(value)
        if msg:
            violations.append(msg)

    if violations:
        violation_detail = "; ".join(violations)
        raise PipelineError(
            code="variants.cross_reference",
            message=(
                f"Variant artifact contains cross-variant path references: {violation_detail}"
            ),
            remediation=(
                "Ensure the variants stage writes Desktop assets only under "
                "Content/<Category>/<Name>/Desktop/ and Mobile assets only under "
                "Content/<Category>/<Name>/Mobile/.  Never reference paths from the "
                "opposite variant directory."
            ),
            stage="variants",
        )
