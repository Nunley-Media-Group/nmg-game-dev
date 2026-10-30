"""Finalize entry points: the ``python -m nmg_game_dev.finalize`` CLI and the MCP tools (#69).

Both use ``FinalizeService`` and the pipeline's job layer, so they share one implementation.
"""

from __future__ import annotations

from .mcp_tools import finalize_asset, get_finalize_job, run_finalize_step
from .service import FinalizeService, build_request, default_budgets_path

__all__ = [
    "FinalizeService",
    "build_request",
    "default_budgets_path",
    "finalize_asset",
    "get_finalize_job",
    "run_finalize_step",
]
