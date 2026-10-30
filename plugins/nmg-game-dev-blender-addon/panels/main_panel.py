from __future__ import annotations

import json
from typing import Any

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

        if props is not None and props.last_result:
            layout.separator()
            for line in _summary_lines(props.last_result):
                layout.label(text=line)


def _summary_lines(raw: str) -> list[str]:
    try:
        data: Any = json.loads(raw)
    except ValueError:
        return ["Last result: unreadable"]
    if "poly_count_desktop" in data:
        return [
            f"Desktop: {data['poly_count_desktop']} triangles",
            f"Mobile: {data['poly_count_mobile']} triangles, {data['mobile']['lod_levels']} LOD(s)",
            f"Exported: {data['desktop_path']}",
        ]
    if "tris_after" in data:
        return [f"Cleanup: {data['tris_before']} -> {data['tris_after']} triangles"]
    if "lod_tris" in data:
        return [f"Mobile LOD0: {data['tris']} triangles, {data['lod_levels']} LOD(s)"]
    return ["Last result: unknown format"]
