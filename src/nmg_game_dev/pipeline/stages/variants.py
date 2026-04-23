"""Variants stage — produce Desktop + Mobile mesh outputs via Blender MCP.

Desktop variant: structural-cleanup-only, no poly reduction, no texture bake.
Mobile variant: decimated, LOD-chained, texture-baked, bone-reduced.

The sidecar records poly counts, texture byte totals, and the computed target
paths for both variants — data consumed by the quality stage and the
``import_ue`` stage respectively.
"""

from __future__ import annotations

from pathlib import Path

import nmg_game_dev.variants as variant_helpers

from ._base import StageArtifact, StageContext
from ._mcp import as_int, translate_mcp_errors

_STAGE = "variants"


def variants(ctx: StageContext) -> StageArtifact:
    """Produce Desktop + Mobile mesh outputs via the Blender MCP.

    Calls ``ctx.mcp_clients.blender`` to apply desktop (structural) and
    mobile (decimation + bake) operations.  Uses
    ``nmg_game_dev.variants.{desktop_path,mobile_path}`` helpers to compute
    target directories and ``assert_no_cross_reference`` before returning.

    The sidecar carries the data the quality stage needs:
    ``poly_count_desktop``, ``poly_count_mobile``, ``texture_bytes_desktop``,
    ``texture_bytes_mobile``, ``desktop_path``, ``mobile_path``.

    Args:
        ctx: Stage execution context.

    Returns:
        A ``StageArtifact`` whose ``blob_path`` points at the desktop mesh
        (canonical primary output) and whose ``sidecar`` carries full variant
        metadata.

    Raises:
        PipelineError: On Blender MCP failures or cross-reference violations.
    """
    upstream_path = (
        str(ctx.upstream_artifact.blob_path) if ctx.upstream_artifact is not None else ""
    )

    # Use a deterministic content root derived from the cache dir so tests
    # can inspect paths without touching real filesystem locations.
    content_root = ctx.cache_dir.parent / "content"

    desktop_dir = variant_helpers.desktop_path(content_root, ctx.prompt)
    mobile_dir = variant_helpers.mobile_path(content_root, ctx.prompt)

    script = (
        f"produce_variants("
        f"mesh_path={upstream_path!r}, "
        f"name={ctx.prompt.name!r}, "
        f"desktop_dir={str(desktop_dir)!r}, "
        f"mobile_dir={str(mobile_dir)!r}"
        f")"
    )
    with translate_mcp_errors(server="blender", stage=_STAGE):
        result = ctx.mcp_clients.blender.run_script(script)

    default_desktop = str(desktop_dir / f"SM_{ctx.prompt.name}.fbx")
    default_mobile = str(mobile_dir / f"SM_{ctx.prompt.name}.fbx")

    desktop_raw = result.get("desktop_path", default_desktop)
    mobile_raw = result.get("mobile_path", default_mobile)
    desktop_path_raw = desktop_raw if isinstance(desktop_raw, str) else default_desktop
    mobile_path_raw = mobile_raw if isinstance(mobile_raw, str) else default_mobile

    sidecar: dict[str, object] = {
        "desktop_path": desktop_path_raw,
        "mobile_path": mobile_path_raw,
        "poly_count_desktop": as_int(result.get("poly_count_desktop")),
        "poly_count_mobile": as_int(result.get("poly_count_mobile")),
        "texture_bytes_desktop": as_int(result.get("texture_bytes_desktop")),
        "texture_bytes_mobile": as_int(result.get("texture_bytes_mobile")),
        "variant": "desktop",  # primary blob is desktop
    }

    artifact = StageArtifact(
        stage=_STAGE,
        blob_path=Path(desktop_path_raw),
        sidecar=sidecar,
    )

    # Guard against cross-variant leaks before returning.
    variant_helpers.assert_no_cross_reference(artifact)

    return artifact
