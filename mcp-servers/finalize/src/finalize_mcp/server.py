"""The ``finalize`` MCP server (#69).

Registers four tools over ``nmg_game_dev``: ``finalize_asset``, ``run_finalize_step``,
``get_finalize_job``, and ``import_audio`` (#155).  The tool logic lives in the package, so the CLI
and this server share one implementation.  stdout is the MCP channel, so logs go to stderr only.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from nmg_game_dev.finalize import finalize_asset as _finalize_asset
from nmg_game_dev.finalize import get_finalize_job as _get_finalize_job
from nmg_game_dev.finalize import import_audio as _import_audio
from nmg_game_dev.finalize import run_finalize_step as _run_finalize_step

logger = logging.getLogger("finalize_mcp")
mcp = FastMCP("finalize")


def _logged(response: dict[str, Any]) -> dict[str, Any]:
    error = response.get("error")
    if isinstance(error, dict):
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
    force: bool = False,
    wait_seconds: float = 0,
    requests: list[dict[str, Any]] | None = None,
    fail_fast: bool = False,
    wait_for_lock: bool = False,
    lock_wait_seconds: float | None = None,
    pie_mode: str = "wait",
    pie_wait_seconds: float = 600,
) -> dict[str, Any]:
    """Finalize an authored collection, or a batch, through every step and import it into Unreal.

    Pass exactly one of collection (with export_root) or requests, a list of finalize requests
    that run one at a time in order under one job lock. Each request takes the same keys as
    collection, and the top-level category, asset_class, export_root, blend, budgets_path, and
    pie options fill in any a request omits. fail_fast skips the rest of a batch after a failed
    collection, and by default the rest still run. wait_for_lock waits for another finalize job
    to release the lock, for at most lock_wait_seconds, instead of failing with
    finalize.job_running. pie_mode is wait (default) or refuse: an import waits up to
    pie_wait_seconds for the Play In Editor session to end, or fails with import_ue.editor_busy.
    Unreal import timeouts are retried with back-off (NMG_GAME_DEV_UE_RETRIES, default 4, and
    NMG_GAME_DEV_UE_RETRY_DELAY_S, default 20).

    Returns {"job_id", "status"} at once. When wait_seconds (0-150) is given and the job finishes in
    time, the result is included: for a batch, result.batch lists each collection's state and any
    failure's code, message, and stage, with succeeded, failed, and skipped counts. Poll
    get_finalize_job for progress, which reports the batch's current collection and completed count.
    """
    return _logged(
        _finalize_asset(
            collection=collection,
            category=category,
            asset_class=asset_class,
            export_root=export_root,
            blend=blend,
            budgets_path=budgets_path,
            force=force,
            wait_seconds=wait_seconds,
            requests=requests,
            fail_fast=fail_fast,
            wait_for_lock=wait_for_lock,
            lock_wait_seconds=lock_wait_seconds,
            pie_mode=pie_mode,
            pie_wait_seconds=pie_wait_seconds,
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
    force: bool = False,
    wait_seconds: float = 0,
    wait_for_lock: bool = False,
    lock_wait_seconds: float | None = None,
    pie_mode: str = "wait",
    pie_wait_seconds: float = 600,
) -> dict[str, Any]:
    """Run one step: validate, bake, variants, export, reimport, or import_ue.

    The step runs through the same implementation finalize_asset uses. Earlier steps it depends on
    run first, from the cache when they are already there. wait_for_lock, lock_wait_seconds, and
    the pie options behave as they do for finalize_asset: a wait for the job lock is bounded by
    lock_wait_seconds, and import_ue fails with import_ue.editor_busy when PIE stays on.
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
            force=force,
            wait_seconds=wait_seconds,
            wait_for_lock=wait_for_lock,
            lock_wait_seconds=lock_wait_seconds,
            pie_mode=pie_mode,
            pie_wait_seconds=pie_wait_seconds,
        )
    )


@mcp.tool(name="get_finalize_job")
def get_finalize_job(job_id: str) -> dict[str, Any]:
    """Return a job's state, step, progress, message, batch progress, and result or error.

    For a batch, batch reports the total, the completed count, the current collection and its
    index, and each item's state. An unknown id returns finalize.job_not_found."""
    return _logged(_get_finalize_job(job_id))


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
