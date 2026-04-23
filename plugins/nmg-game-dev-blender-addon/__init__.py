from __future__ import annotations

import bpy

from .operators import (
    NMGGAMEDEV_OT_cleanup_desktop,
    NMGGAMEDEV_OT_generate_variants,
    NMGGAMEDEV_OT_optimize_mobile,
)
from .panels import NMGGAMEDEV_PT_main_panel
from .property_groups import NmgGameDevPipelineProps
from .utils.version import version_tuple

bl_info = {
    "name": "NMG Game Dev",
    "author": "Nunley Media Group",
    "version": version_tuple(),
    "blender": (4, 2, 0),
    "category": "Pipeline",
    "description": (
        "Blender-first content pipeline operators for NMG games. "
        "Exposes stub operators invokable via the ahujasid/blender-mcp host."
    ),
    "doc_url": "https://github.com/nunleymediagroup/nmg-game-dev",
    "support": "COMMUNITY",
}

# Property group must precede operators and panel so draw() never encounters
# a missing Scene.nmg_game_dev pointer.
REGISTER_CLASSES: tuple[type, ...] = (
    NmgGameDevPipelineProps,
    NMGGAMEDEV_OT_cleanup_desktop,
    NMGGAMEDEV_OT_optimize_mobile,
    NMGGAMEDEV_OT_generate_variants,
    NMGGAMEDEV_PT_main_panel,
)


def register() -> None:
    for cls in REGISTER_CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.nmg_game_dev = bpy.props.PointerProperty(  # type: ignore[assignment]
        type=NmgGameDevPipelineProps
    )


def unregister() -> None:
    if hasattr(bpy.types.Scene, "nmg_game_dev"):
        del bpy.types.Scene.nmg_game_dev
    for cls in reversed(REGISTER_CLASSES):
        bpy.utils.unregister_class(cls)
