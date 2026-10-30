"""Shared operator pieces: the asset-class enum and last-result storage."""

from __future__ import annotations

import json
from typing import Any

import bpy

ASSET_CLASS_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("small_prop", "Small prop", "Bottle, key (contract section 6)"),
    ("standard_prop", "Standard prop", "Chest, lamppost, fence segment"),
    ("hero_prop", "Hero prop", "Vehicle, set piece"),
    ("character", "Character", "Humanoid, creature"),
    ("environment_piece", "Environment piece", "Building, road or track section (tiling)"),
)


def store_last_result(context: bpy.types.Context, result: dict[str, Any]) -> None:
    context.scene.nmg_game_dev.last_result = json.dumps(result, indent=2, sort_keys=True)


def store_rig_result(context: bpy.types.Context, result: dict[str, Any]) -> None:
    """Store a rig_core result exactly as the direct call returned it (sorted keys)."""
    context.scene.nmg_game_dev.last_result = json.dumps(result, sort_keys=True)
