"""Texture stage: bake the authored materials to contract texture sets via the Blender MCP (#67).

Sends one script through ``ctx.mcp_clients.blender.run_script`` that calls
``bake_core.run_for_mcp``. A bake error comes back as an ``error`` dict and is raised as
``PipelineError`` with the stage ``texture``. A result carries the texture paths, byte totals,
proof metrics, and a one-line summary in the sidecar.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..errors import PipelineError
from ._base import StageArtifact, StageContext
from ._mcp import as_int, require_str_field, translate_mcp_errors

_STAGE = "texture"
_BUDGET_FILE = "nmg-budgets.json"


def texture(ctx: StageContext) -> StageArtifact:
    """Bake the prompt's collection through the Blender MCP and return the texture artifact.

    Raises:
        PipelineError: ``texture.bake_failed`` (or the bake's own code) when the bake refuses,
            ``mcp.blender.unreachable`` on connection failure, and
            ``mcp.blender.invalid_response`` when the result has no manifest path.
    """
    asset_class = "hero_prop" if ctx.prompt.tier == "hero" else "standard_prop"
    out_dir = ctx.cache_dir / "work" / "texture" / ctx.prompt.category / ctx.prompt.name
    script = (
        "from nmg_game_dev_blender_addon.bake_core import run_for_mcp\n"
        "result = run_for_mcp("
        f"collection={ctx.prompt.name!r}, "
        f"asset_class={asset_class!r}, "
        f"out_dir={str(out_dir)!r}, "
        f"budgets_path={_budgets_path()!r})"
    )
    with translate_mcp_errors(server="blender", stage=_STAGE):
        result = ctx.mcp_clients.blender.run_script(script)

    error = result.get("error")
    if isinstance(error, dict):
        raise PipelineError(
            code=str(error.get("code", "texture.bake_failed")),
            message=str(error.get("message", "The bake failed.")),
            remediation=str(error.get("remediation", "Check the Blender log, then rerun.")),
            stage=_STAGE,
        )

    manifest_path = require_str_field(result, "manifest_path", server="blender", stage=_STAGE)
    sidecar: dict[str, object] = {
        "upstream_stage": ctx.upstream_artifact.stage if ctx.upstream_artifact else None,
        "name": ctx.prompt.name,
        "category": ctx.prompt.category,
        "class": asset_class,
        "mode": str(result.get("mode", "")),
        "cache_hit": result.get("cache_hit") is True,
        "desktop_dir": str(result.get("desktop_dir", "")),
        "mobile_dir": str(result.get("mobile_dir", "")),
        "desktop_textures": _strings(result.get("desktop_textures")),
        "mobile_textures": _strings(result.get("mobile_textures")),
        "texture_bytes_desktop": as_int(result.get("texture_bytes_desktop")),
        "texture_bytes_mobile": as_int(result.get("texture_bytes_mobile")),
        "materials": result.get("materials", []),
        "proof": result.get("proof", {}),
        "summary": str(result.get("summary", "")),
    }
    return StageArtifact(stage=_STAGE, blob_path=Path(manifest_path), sidecar=sidecar)


def _budgets_path() -> str | None:
    """nmg-budgets.json in the project root when present, else None (contract defaults)."""
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    candidate = root / _BUDGET_FILE
    return str(candidate) if candidate.is_file() else None


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
