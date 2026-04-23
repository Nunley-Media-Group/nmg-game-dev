from __future__ import annotations

import bpy

from ..utils.logging import log_stub_invocation


class NMGGAMEDEV_OT_optimize_mobile(bpy.types.Operator):
    bl_idname = "nmggamedev.optimize_mobile"
    bl_label = "Optimize for Mobile variant"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        log_stub_invocation("nmggamedev.optimize_mobile")
        return {"FINISHED"}
