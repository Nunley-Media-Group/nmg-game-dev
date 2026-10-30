"""ShipError: the error the ship flow raises for a failed gate, script, or precondition (#6).

``stage`` names the ship step that failed, e.g. ``preflight``, ``build``, or ``notarize``.
"""

from __future__ import annotations

from nmg_game_dev.pipeline.errors import PipelineError


class ShipError(PipelineError):
    """A ship step failed. Carries the stable ``code`` and the ``remediation`` to show."""

    def __init__(self, code: str, message: str, remediation: str, stage: str = "ship") -> None:
        super().__init__(code=code, message=message, remediation=remediation, stage=stage)
