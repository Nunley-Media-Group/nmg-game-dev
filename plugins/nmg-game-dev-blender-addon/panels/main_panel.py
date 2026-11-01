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
        layout.separator()
        layout.operator("nmggamedev.validate_contract")
        layout.operator("nmggamedev.reimport_check")
        layout.operator("nmggamedev.render_review")
        layout.operator("nmggamedev.inspect_spatial")
        layout.separator()
        layout.operator("nmggamedev.bake_materials")
        layout.separator()
        layout.operator("nmggamedev.rig_humanoid")
        layout.operator("nmggamedev.import_animations")
        layout.operator("nmggamedev.export_rigged")

        if props is not None and props.last_result:
            layout.separator()
            for line in _summary_lines(props.last_result):
                layout.label(text=line)


def _summary_lines(raw: str) -> list[str]:
    try:
        data: Any = json.loads(raw)
    except ValueError:
        return ["Last result: unreadable"]
    if data.get("kind") == "bake":
        return [data["summary"], f"Bake manifest: {data['manifest_path']}"]
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
    if data.get("kind") in {"contract", "reimport", "inspect"}:
        verdict = "PASS" if data["passed"] else "FAIL"
        return [
            f"{data['kind'].title()} {data['asset']}: {verdict}",
            f"{len(data['findings'])} finding(s)",
        ]
    if "files" in data:
        return [f"Review renders: {len(data['files'])} file(s)"]
    if "status" in data:
        lines = [f"Rig result: {data['status']}"]
        if "code" in data:
            lines.append(data["code"])
        return lines
    return ["Last result: unknown format"]
