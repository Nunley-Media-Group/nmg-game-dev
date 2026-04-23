"""Pipeline stage types — re-exported for convenient import by callers.

Import from here rather than from ``_base`` directly::

    from nmg_game_dev.pipeline.stages import Stage, StageArtifact, StageContext
"""

from __future__ import annotations

from ._base import McpClients, Stage, StageArtifact, StageContext

__all__ = ["McpClients", "Stage", "StageArtifact", "StageContext"]
