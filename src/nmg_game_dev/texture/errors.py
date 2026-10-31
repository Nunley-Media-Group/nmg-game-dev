"""TextureGenError: the error the local texture generation flow raises (#7).

``code`` uses the ``texture.<condition>`` convention. ``remediation`` is the copy-pasteable next
action shown to the developer.
"""

from __future__ import annotations

from nmg_game_dev.pipeline.errors import PipelineError


class TextureGenError(PipelineError):
    """A texture generation step failed. Carries the stable ``code`` and the ``remediation``."""

    def __init__(
        self,
        code: str,
        message: str,
        remediation: str,
        stage: str = "texture_gen",
    ) -> None:
        super().__init__(code=code, message=message, remediation=remediation, stage=stage)
