"""AudioError: the error the audio import raises (#155).

``code`` uses the ``audio.<condition>`` convention. ``remediation`` is the copy-pasteable next
action the developer sees. An Unreal reachability failure keeps its own ``mcp.unreal.unreachable``
code, because ``import_audio`` turns that one into a warning instead of an error.
"""

from __future__ import annotations

from nmg_game_dev.pipeline.errors import PipelineError


class AudioError(PipelineError):
    """An audio import step failed. Carries the stable ``code`` and the ``remediation``."""

    def __init__(
        self,
        code: str,
        message: str,
        remediation: str,
        stage: str = "audio",
    ) -> None:
        super().__init__(code=code, message=message, remediation=remediation, stage=stage)
