"""Generate stage — produces the initial 3D mesh via the Blender MCP.

``generate_blender`` is the only generation source; ``pipeline.run()`` uses it
as the ``generate`` stage.  All downstream stages are source-agnostic.

The function satisfies the ``Stage`` Protocol (callable that accepts a
``StageContext`` and returns a ``StageArtifact``).
"""

from __future__ import annotations

from pathlib import Path

from ._base import StageArtifact, StageContext
from ._mcp import require_str_field, translate_mcp_errors

_STAGE = "generate"


def generate_blender(ctx: StageContext) -> StageArtifact:
    """Generate an initial mesh via the Blender MCP.

    Raises:
        PipelineError: On any Blender MCP connectivity or execution failure.
    """
    script = (
        f"generate_mesh("
        f"category={ctx.prompt.category!r}, "
        f"name={ctx.prompt.name!r}, "
        f"tier={ctx.prompt.tier!r}, "
        f"description={ctx.prompt.description!r}"
        f")"
    )
    with translate_mcp_errors(server="blender", stage=_STAGE):
        result = ctx.mcp_clients.blender.run_script(script)

    output_path = require_str_field(result, "output_path", server="blender", stage=_STAGE)
    sidecar: dict[str, object] = {
        "source": "blender",
        "category": ctx.prompt.category,
        "name": ctx.prompt.name,
        "tier": ctx.prompt.tier,
    }
    return StageArtifact(stage=_STAGE, blob_path=Path(output_path), sidecar=sidecar)
