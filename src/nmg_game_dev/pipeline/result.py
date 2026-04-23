"""PipelineResult — the value returned by ``pipeline.run()``.

Carries the final Desktop + Mobile variant paths and per-stage execution
bookkeeping so callers can distinguish cache hits from real MCP invocations.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class PipelineResult(BaseModel):
    """Outcome of a successful ``pipeline.run()`` call.

    Attributes:
        desktop_path: Absolute path to the imported desktop variant in the
            consumer project's ``Content/<Category>/<Name>/Desktop/`` folder.
        mobile_path: Absolute path to the imported mobile variant in the
            consumer project's ``Content/<Category>/<Name>/Mobile/`` folder.
        stages_executed: Names of stages that actually ran (i.e. cache miss).
        cache_hits: Names of stages whose artifact was served from cache.
    """

    desktop_path: Path
    mobile_path: Path
    stages_executed: list[str]
    cache_hits: list[str]
