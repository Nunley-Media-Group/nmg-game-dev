"""Inspect core: part relationships, manifoldness, and triangle headroom for one asset collection.

Shared by the nmggamedev.inspect_spatial operator and the model-asset skill's
execute_blender_code snippets. Failures raise ContractError with inspect.* codes.
"""

from __future__ import annotations

from .spatial import DEFAULT_GAP_TOLERANCE, INSPECT_RULES, inspect_asset

__all__ = ["DEFAULT_GAP_TOLERANCE", "INSPECT_RULES", "inspect_asset"]
