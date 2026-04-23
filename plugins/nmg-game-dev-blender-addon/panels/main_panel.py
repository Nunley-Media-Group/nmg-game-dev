from __future__ import annotations

import bpy


class NMGGAMEDEV_PT_main_panel(bpy.types.Panel):
    bl_idname = "NMGGAMEDEV_PT_main_panel"
    bl_label = "NMG Game Dev"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "NMG"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        scene = context.scene
        props = getattr(scene, "nmg_game_dev", None)

        if props is not None:
            layout.prop(props, "variant")
            layout.prop(props, "preset")
            layout.separator()

        layout.operator("nmggamedev.cleanup_desktop")
        layout.operator("nmggamedev.optimize_mobile")
        layout.operator("nmggamedev.generate_variants")
