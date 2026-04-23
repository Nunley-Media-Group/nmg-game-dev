from __future__ import annotations

import bpy

from ..utils.logging import log_stub_invocation


class NMGGAMEDEV_OT_generate_variants(bpy.types.Operator):
    bl_idname = "nmggamedev.generate_variants"
    bl_label = "Generate Desktop + Mobile variants"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        log_stub_invocation("nmggamedev.generate_variants")
        return {"FINISHED"}
