"""MeshyError: the error the optional Meshy flow raises (#98).

``code`` uses the ``meshy.<condition>`` convention. ``remediation`` is the copy-pasteable next
action shown to the developer. Messages and remediations never contain the API key.
"""

from __future__ import annotations

from nmg_game_dev.pipeline.errors import PipelineError


class MeshyError(PipelineError):
    """A Meshy step failed. Carries the stable ``code`` and the ``remediation``."""

    def __init__(
        self,
        code: str,
        message: str,
        remediation: str,
        stage: str = "meshy",
    ) -> None:
        super().__init__(code=code, message=message, remediation=remediation, stage=stage)
