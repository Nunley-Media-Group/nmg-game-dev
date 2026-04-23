"""Generate stage — produces the initial 3D mesh via Blender or Meshy MCP.

This is the only stage that branches on ``source``.  The ``pipeline.run()``
orchestrator picks ``generate_blender`` or ``generate_meshy`` based on the
``source`` argument; all downstream stages are source-agnostic.

Both functions satisfy the ``Stage`` Protocol (callable that accepts a
``StageContext`` and returns a ``StageArtifact``).
"""

from __future__ import annotations

from pathlib import Path

from ..errors import PipelineError
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


def generate_meshy(ctx: StageContext) -> StageArtifact:
    """Generate an initial mesh via the Meshy MCP (supplement source).

    Raises:
        PipelineError: When the Meshy client is absent or a connectivity/API
            failure occurs.
    """
    if ctx.mcp_clients.meshy is None:
        raise PipelineError(
            code="mcp.meshy.unreachable",
            message="Meshy MCP client is not configured (meshy=None in McpClients)",
            remediation=(
                "Set the MESHY_API_KEY environment variable and ensure the Meshy "
                "MCP server is listed in .mcp.json.  Pass a configured McpClients "
                "with a non-None meshy field."
            ),
            stage=_STAGE,
        )

    generation_prompt = (
        f"{ctx.prompt.tier} {ctx.prompt.category} named {ctx.prompt.name}: {ctx.prompt.description}"
    )
    with translate_mcp_errors(server="meshy", stage=_STAGE):
        result = ctx.mcp_clients.meshy.generate(generation_prompt)

    output_path = require_str_field(result, "output_path", server="meshy", stage=_STAGE)
    sidecar: dict[str, object] = {
        "source": "meshy",
        "category": ctx.prompt.category,
        "name": ctx.prompt.name,
        "tier": ctx.prompt.tier,
    }
    return StageArtifact(stage=_STAGE, blob_path=Path(output_path), sidecar=sidecar)
