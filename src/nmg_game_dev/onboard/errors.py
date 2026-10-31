"""OnboardError: the error onboarding raises before or during a consumer write (#7).

``code`` is ``onboard.<condition>``. Preflight failures are raised before the first consumer write,
so a failed run leaves the consumer directory unchanged.
"""

from __future__ import annotations

from nmg_game_dev.pipeline.errors import PipelineError


class OnboardError(PipelineError):
    """An onboarding step failed. Carries the stable ``code`` and the ``remediation`` to show."""

    def __init__(self, code: str, message: str, remediation: str, stage: str = "onboard") -> None:
        super().__init__(code=code, message=message, remediation=remediation, stage=stage)
