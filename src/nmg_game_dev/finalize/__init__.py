"""Finalize entry points: the ``python -m nmg_game_dev.finalize`` CLI and the MCP tools (#69).

Both use ``FinalizeService`` and the pipeline's job layer, so they share one implementation.
"""

from __future__ import annotations

from .mcp_tools import (
    check_finalized,
    finalize_asset,
    game_screenshot,
    get_finalize_job,
    import_audio,
    list_material_variants,
    reduce_asset,
    refresh_audio_table,
    run_finalize_step,
)
from .service import FinalizeService, build_request, default_budgets_path

__all__ = [
    "FinalizeService",
    "check_finalized",
    "build_request",
    "default_budgets_path",
    "finalize_asset",
    "game_screenshot",
    "get_finalize_job",
    "import_audio",
    "list_material_variants",
    "reduce_asset",
    "refresh_audio_table",
    "run_finalize_step",
]
