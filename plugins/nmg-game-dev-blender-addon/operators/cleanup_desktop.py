from __future__ import annotations

import bpy

from ..utils.logging import log_stub_invocation


class NMGGAMEDEV_OT_cleanup_desktop(bpy.types.Operator):
    bl_idname = "nmggamedev.cleanup_desktop"
    bl_label = "Clean up for Desktop variant"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        log_stub_invocation("nmggamedev.cleanup_desktop")
        return {"FINISHED"}
