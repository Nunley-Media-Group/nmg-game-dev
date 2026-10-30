"""Bake core: bake authored materials into contract-compliant UV texture sets (#67).

The operator, the agent's execute_blender_code calls, and the pipeline texture stage all reach
bake_asset (or run_for_mcp, which returns the error dict instead of raising). Every failure is a
BakeError with a stable code, reason, message, and remediation, and the file is restored.
"""

from __future__ import annotations

from .core import bake_asset, run_for_mcp
from .errors import BakeError

__all__ = ["BakeError", "bake_asset", "run_for_mcp"]
