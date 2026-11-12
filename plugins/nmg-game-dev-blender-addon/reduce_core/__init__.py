"""Reduce core: reduce a generated high-poly asset to its Desktop budget (#139).

The panel operator, the agent's execute_blender_code calls, and the finalize reduce job all reach
reduce_asset (or run_for_mcp, which returns the error dict instead of raising). plan.py is pure
Python and loads by path under CPython; the rest needs Blender.
"""

from __future__ import annotations

from .core import reduce_asset, run_for_mcp
from .plan import DEFAULTS, ReduceError

__all__ = ["DEFAULTS", "ReduceError", "reduce_asset", "run_for_mcp"]
