"""The ``finalize`` MCP server (#69).

Registers ten tools over ``nmg_game_dev``: ``finalize_asset``, ``run_finalize_step``,
``reduce_asset`` (#139), ``get_finalize_job``, ``list_material_variants`` (#148), ``import_audio``
(#155), ``refresh_audio_table`` (#237), ``game_screenshot`` (#251), and ``check_finalized`` (#247).
The tool logic lives in the package, so the CLI and this server share one implementation.  stdout
is the MCP channel, so logs go to stderr only.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from nmg_game_dev.finalize import check_finalized as _check_finalized
from nmg_game_dev.finalize import finalize_asset as _finalize_asset
from nmg_game_dev.finalize import game_screenshot as _game_screenshot
from nmg_game_dev.finalize import get_finalize_job as _get_finalize_job
from nmg_game_dev.finalize import import_audio as _import_audio
from nmg_game_dev.finalize import list_material_variants as _list_material_variants
from nmg_game_dev.finalize import reduce_asset as _reduce_asset
from nmg_game_dev.finalize import refresh_audio_table as _refresh_audio_table
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
    collection: str | None = None,
    export_root: str | None = None,
    category: str | None = None,
    asset_class: str | None = None,
    blend: str | None = None,
    budgets_path: str | None = None,
    material_variants_path: str | None = None,
    force: bool = False,
    wait_seconds: float = 0,
    requests: list[dict[str, Any]] | None = None,
    fail_fast: bool = False,
    wait_for_lock: bool = False,
    lock_wait_seconds: float | None = None,
    compatible_with: list[str] | None = None,
    skip_up_to_date: bool = False,
) -> dict[str, Any]:
    """Finalize an authored collection, or a batch, through every step and import it into Godot.

    Pass exactly one of collection or requests, a list of finalize requests that run one at a time
    in order under one job lock. Each request takes the same keys as collection, and the top-level
    category, asset_class, export_root, blend, and budgets_path fill in any a request omits.
    export_root defaults to <project>/game/assets. import_godot runs godot --headless --import once
    and probes each variant; it fails with godot.not_found, import_godot.project_missing,
    import_godot.import_failed, import_godot.mismatch, or import_godot.terrain_height_mismatch.
    fail_fast skips the rest of a batch after a failed collection, and by default the rest still
    run. skip_up_to_date (batch only) skips each collection that check_finalized reports up to date,
    counting it under result.batch.up_to_date. wait_for_lock waits for another finalize job to
    release the lock, for at most lock_wait_seconds, instead of failing with finalize.job_running.

    Returns {"job_id", "status"} at once. When wait_seconds (0-150) is given and the job finishes in
    time, the result is included: for a batch, result.batch lists each collection's state and any
    failure's code, message, and stage, with succeeded, failed, and skipped counts. Poll
    get_finalize_job for progress, which reports the batch's current collection and completed count.
    material_variants_path names a <Name>.material-variants.json declaration; without it, one beside
    blend is used when present. In a batch, each request entry sets its own material_variants_path.
    compatible_with lists <Category>/<Name> characters whose skeleton this character's clips may
    also play on; in a batch, each request entry sets its own compatible_with.
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
            requests=requests,
            fail_fast=fail_fast,
            wait_for_lock=wait_for_lock,
            lock_wait_seconds=lock_wait_seconds,
            compatible_with=compatible_with,
            skip_up_to_date=skip_up_to_date,
        )
    )


@mcp.tool(name="run_finalize_step")
def run_finalize_step(
    step: str,
    collection: str,
    export_root: str | None = None,
    category: str | None = None,
    asset_class: str | None = None,
    blend: str | None = None,
    budgets_path: str | None = None,
    material_variants_path: str | None = None,
    force: bool = False,
    wait_seconds: float = 0,
    wait_for_lock: bool = False,
    lock_wait_seconds: float | None = None,
    compatible_with: list[str] | None = None,
) -> dict[str, Any]:
    """Run one step: validate, bake, variants, export, export_anims, reimport, import_godot, or
    import_anims.

    The step runs through the same implementation finalize_asset uses. Earlier steps it depends on
    run first, from the cache when they are already there. wait_for_lock and lock_wait_seconds
    behave as they do for finalize_asset. export_root defaults to <project>/game/assets.
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
            wait_for_lock=wait_for_lock,
            lock_wait_seconds=lock_wait_seconds,
            compatible_with=compatible_with,
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
    """Return a job's state, step, progress, message, batch progress, and result or error.

    For a batch, batch reports the total, the completed count, the current collection and its
    index, and each item's state. An unknown id returns finalize.job_not_found."""
    return _logged(_get_finalize_job(job_id))


@mcp.tool(name="check_finalized")
def check_finalized(
    category: str | None = None,
    collection: str | None = None,
    assets: list[dict[str, str]] | None = None,
    export_root: str | None = None,
) -> dict[str, Any]:
    """Say whether assets are up to date, from their finalize records, without running anything.

    Pass one category and collection, or assets as a list of {category, collection} objects, not
    both. Returns {"assets": [...]} with, per asset, category, collection, up_to_date, reason, and
    record: {state, ended_at, error_code}, or null without a record. Reasons are up_to_date,
    no_record, record_unreadable, last_run_failed, not_full_run, no_source_blend, source_missing,
    source_newer, import_missing, and project_missing. The check reads only the record and file
    times: it starts no Blender or Godot and takes no cache lock. export_root defaults to
    <project>/game/assets.
    """
    return _logged(
        _check_finalized(
            category=category, collection=collection, assets=assets, export_root=export_root
        )
    )


@mcp.tool(name="list_material_variants")
def list_material_variants(category: str, collection: str, export_root: str | None = None) -> Any:
    """List a finalized asset's material variants, for Desktop and Mobile, without running Godot.

    Reads <export_root>/<Category>/<Name>/nmg-variants.json (export_root defaults to
    <project>/game/assets) and the M_<Name>_<Part>_<Variant>.tres files finalize wrote. Returns rows
    of {name, material, desktop, mobile}, where desktop and mobile are the res:// path of the
    variant's .tres in each folder or null, sorted by material then name. An asset with no material
    variants returns []. A missing or invalid sidecar returns finalize.material_variants_failed.
    """
    return _logged(
        _list_material_variants(category=category, collection=collection, export_root=export_root)
    )


@mcp.tool(name="import_audio")
def import_audio(
    file: str,
    name: str,
    kind: str,
    loop: bool | None = None,
    max_seconds: float | None = None,
    loudness_lufs: float | None = None,
    loop_crossfade_ms: int | None = None,
    finish: bool | None = None,
) -> dict[str, Any]:
    """Import a saved ElevenLabs sound effect or music file into the Godot project.

    kind is "sfx" or "music"; name is PascalCase. The file (.wav, .mp3, .ogg, or .flac) is stored
    as a 16-bit WAV under SourceArt/Audio/<SFX|Music>/, and the game copy is finished first unless
    finish is false: leading silence below -50 dBFS is trimmed, max_seconds cuts it with a 20 ms
    fade-out, loop_crossfade_ms (default 500) crossfades a looping seam, and loudness is matched to
    loudness_lufs (default -16 for sfx, -18 for music). A sound effect is copied to
    game/assets/Audio/<name>.wav and imported as an AudioStreamWAV; music is encoded with ffmpeg to
    game/assets/Audio/<name>.ogg and imported as an AudioStreamOggVorbis, looping when loop is
    true. loop and the finishing settings are stored per sound and reused when omitted (loop
    defaults to false). The result names godot_asset,
    imported_to_godot, finish, settings, and refreshed_tables. A failure returns {"error": {code,
    message, remediation, stage}}.
    """
    return _logged(
        _import_audio(
            file=file,
            name=name,
            kind=kind,
            loop=loop,
            max_seconds=max_seconds,
            loudness_lufs=loudness_lufs,
            loop_crossfade_ms=loop_crossfade_ms,
            finish=finish,
        )
    )


@mcp.tool(name="refresh_audio_table")
def refresh_audio_table(project: str | None = None) -> dict[str, Any]:
    """Rewrite each Audio component's name table from the imported sounds and the design backlog.

    Reads the sounds under game/assets/Audio/ and the region music fields in the design backlog,
    and rewrites every game/systems/*/audio_table.tres that declares NmgAudioTable. Returns
    {"refreshed_tables": [...]}, the project-relative tables whose text changed, or an error object
    with audio.godot_project_missing. project defaults to CLAUDE_PROJECT_DIR, else the working
    directory.
    """
    return _logged(_refresh_audio_table(project=project))


@mcp.tool(name="game_screenshot")
def game_screenshot(
    path: str, after: float = 3, options: list[str] | None = None
) -> dict[str, Any]:
    """Save a PNG of the running consumer game after a delay, for reviewing assets in the engine.

    Runs the Godot project windowed with the launch options (for example "--at=Forest"), so the
    game's own lighting and materials show, and NmgLaunch writes the root viewport to path and
    quits. A relative path resolves against the consumer project. after is 0 to 60 seconds. Returns
    {path, width, height}; a failure returns {"error": {code, message, remediation, stage}} with
    shot.invalid_after, shot.invalid_path, godot.project_missing, godot.not_found, or shot.no_image
    (the game exited without writing the PNG, and the message carries its last output lines).
    """
    return _logged(_game_screenshot(path=path, after=after, options=options))


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
