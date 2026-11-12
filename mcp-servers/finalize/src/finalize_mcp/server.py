"""The ``finalize`` MCP server (#69).

Registers six tools over ``nmg_game_dev``: ``finalize_asset``, ``run_finalize_step``,
``reduce_asset`` (#139), ``get_finalize_job``, ``list_material_variants`` (#148), and
``import_audio`` (#155).  The tool logic lives in the package, so the CLI and this server share one
implementation.  stdout is the MCP channel, so logs go to stderr only.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from nmg_game_dev.finalize import finalize_asset as _finalize_asset
from nmg_game_dev.finalize import get_finalize_job as _get_finalize_job
from nmg_game_dev.finalize import import_audio as _import_audio
from nmg_game_dev.finalize import list_material_variants as _list_material_variants
from nmg_game_dev.finalize import reduce_asset as _reduce_asset
from nmg_game_dev.finalize import run_finalize_step as _run_finalize_step

logger = logging.getLogger("finalize_mcp")
mcp = FastMCP("finalize")


def _logged(response: Any) -> Any:
    if isinstance(response, dict) and isinstance(response.get("error"), dict):
        error = response["error"]
        logger.error("%s: %s", error.get("code"), error.get("message"))
    return response


@mcp.tool(name="finalize_asset")
def finalize_asset(
    collection: str,
    export_root: str,
    category: str | None = None,
    asset_class: str | None = None,
    blend: str | None = None,
    budgets_path: str | None = None,
    material_variants_path: str | None = None,
    force: bool = False,
    wait_seconds: float = 0,
) -> dict[str, Any]:
    """Finalize an authored collection through every step and import it into Unreal.

    Returns {"job_id", "status"} at once. When wait_seconds (0-150) is given and the job finishes in
    time, the result is included. Poll get_finalize_job for progress. material_variants_path names a
    <Name>.material-variants.json declaration; without it, one beside blend is used when present.
    """
    return _logged(
        _finalize_asset(
            collection=collection,
            category=category,
            asset_class=asset_class,
            export_root=export_root,
            blend=blend,
            budgets_path=budgets_path,
            material_variants_path=material_variants_path,
            force=force,
            wait_seconds=wait_seconds,
        )
    )


@mcp.tool(name="run_finalize_step")
def run_finalize_step(
    step: str,
    collection: str,
    export_root: str,
    category: str | None = None,
    asset_class: str | None = None,
    blend: str | None = None,
    budgets_path: str | None = None,
    material_variants_path: str | None = None,
    force: bool = False,
    wait_seconds: float = 0,
) -> dict[str, Any]:
    """Run one step: validate, bake, variants, export, reimport, or import_ue.

    The step runs through the same implementation finalize_asset uses. Earlier steps it depends on
    run first, from the cache when they are already there.
    """
    return _logged(
        _run_finalize_step(
            step=step,
            collection=collection,
            category=category,
            asset_class=asset_class,
            export_root=export_root,
            blend=blend,
            budgets_path=budgets_path,
            material_variants_path=material_variants_path,
            force=force,
            wait_seconds=wait_seconds,
        )
    )


@mcp.tool(name="reduce_asset")
def reduce_asset(
    collection: str,
    asset_class: str,
    blend: str | None = None,
    budgets_path: str | None = None,
    device: str = "GPU",
    cage_extrusion: float | None = None,
    max_ray_distance: float | None = None,
    miss_threshold: float | None = None,
    parts: dict[str, dict[str, Any]] | None = None,
    wait_seconds: float = 0,
) -> dict[str, Any]:
    """Reduce a generated collection to its Desktop triangle budget and bake its look onto it.

    Keeps the originals in the hidden <Name>_High collection. Returns {"job_id", "status"} at once;
    the result is included when the job finishes within wait_seconds (0-150). Poll
    get_finalize_job for progress. asset_class is one of small_prop, standard_prop, hero_prop,
    character, or environment_piece; terrain is refused.
    """
    return _logged(
        _reduce_asset(
            collection=collection,
            asset_class=asset_class,
            blend=blend,
            budgets_path=budgets_path,
            device=device,
            cage_extrusion=cage_extrusion,
            max_ray_distance=max_ray_distance,
            miss_threshold=miss_threshold,
            parts=parts,
            wait_seconds=wait_seconds,
        )
    )


@mcp.tool(name="get_finalize_job")
def get_finalize_job(job_id: str) -> dict[str, Any]:
    """Return a job's state, step, progress, message, and result or error."""
    return _logged(_get_finalize_job(job_id))


@mcp.tool(name="list_material_variants")
def list_material_variants(category: str, collection: str) -> Any:
    """List the material variants Unreal holds for a finalized asset, for Desktop and Mobile.

    Returns rows of {name, material, desktop, mobile}, where desktop and mobile are the variant's
    material instance path in each folder, sorted by material then name. An asset with no material
    variants, or one not in Content, returns []. A failure returns {"error": {...}}.
    """
    return _logged(_list_material_variants(category=category, collection=collection))


@mcp.tool(name="import_audio")
def import_audio(file: str, name: str, kind: str, loop: bool = False) -> dict[str, Any]:
    """Import a saved ElevenLabs sound effect or music file into Unreal as a SoundWave.

    kind is "sfx" or "music"; name is PascalCase. The file (.wav, .mp3, .ogg, or .flac) is stored
    as a 16-bit WAV under SourceArt/Audio/<SFX|Music>/ and imported as
    /Game/Audio/<SFX|Music>/SW_<name>. Returns the result, or {"error": {code, message, remediation,
    stage}}.
    """
    return _logged(_import_audio(file=file, name=name, kind=kind, loop=loop))


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
