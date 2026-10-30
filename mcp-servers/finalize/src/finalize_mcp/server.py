"""The ``finalize`` MCP server (#69).

Registers three tools over ``nmg_game_dev.finalize``: ``finalize_asset``, ``run_finalize_step``, and
``get_finalize_job``.  The tool logic lives in the package, so the CLI and this server share one
implementation.  stdout is the MCP channel, so logs go to stderr only.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from nmg_game_dev.finalize import finalize_asset as _finalize_asset
from nmg_game_dev.finalize import get_finalize_job as _get_finalize_job
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
    collection: str,
    category: str,
    asset_class: str,
    export_root: str,
    blend: str | None = None,
    budgets_path: str | None = None,
    force: bool = False,
    wait_seconds: float = 0,
) -> dict[str, Any]:
    """Finalize an authored collection through every step and import it into Unreal.

    Returns {"job_id", "status"} at once. When wait_seconds (0-150) is given and the job finishes in
    time, the result is included. Poll get_finalize_job for progress.
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
        )
    )


@mcp.tool(name="run_finalize_step")
def run_finalize_step(
    step: str,
    collection: str,
    category: str,
    asset_class: str,
    export_root: str,
    blend: str | None = None,
    budgets_path: str | None = None,
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
            force=force,
            wait_seconds=wait_seconds,
        )
    )


@mcp.tool(name="get_finalize_job")
def get_finalize_job(job_id: str) -> dict[str, Any]:
    """Return a job's state, step, progress, message, and result or error."""
    return _logged(_get_finalize_job(job_id))


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
