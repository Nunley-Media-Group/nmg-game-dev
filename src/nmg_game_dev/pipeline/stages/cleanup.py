"""Cleanup stage — structural mesh cleanup via Blender MCP.

Performs structural cleanup only: removes loose geometry, fixes normals,
merges duplicate vertices, and seeds the LOD chain.  No decimation, no
texture reduction — those operations belong to the variants stage.

Calls only ``ctx.mcp_clients.blender``; no other MCP is touched.
"""

from __future__ import annotations

from pathlib import Path

from ._base import StageArtifact, StageContext
from ._mcp import require_str_field, translate_mcp_errors

_STAGE = "cleanup"


def cleanup(ctx: StageContext) -> StageArtifact:
    """Run structural mesh cleanup via the Blender MCP.

    Raises:
        PipelineError: On Blender MCP connectivity or execution failure.
    """
    upstream_path = (
        str(ctx.upstream_artifact.blob_path) if ctx.upstream_artifact is not None else ""
    )
    script = f"cleanup_mesh(mesh_path={upstream_path!r}, name={ctx.prompt.name!r})"
    with translate_mcp_errors(server="blender", stage=_STAGE):
        result = ctx.mcp_clients.blender.run_script(script)

    output_path = require_str_field(result, "output_path", server="blender", stage=_STAGE)
    sidecar: dict[str, object] = {
        "upstream_stage": ctx.upstream_artifact.stage if ctx.upstream_artifact else None,
        "name": ctx.prompt.name,
    }
    return StageArtifact(stage=_STAGE, blob_path=Path(output_path), sidecar=sidecar)
