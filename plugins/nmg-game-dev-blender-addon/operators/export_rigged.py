from __future__ import annotations

import bpy

from ..rig_core import export_rigged as write_rigged
from ..utils.logging import log_operator_result
from ._common import store_rig_result

_OP_NAME = "nmggamedev.export_rigged"


class NMGGAMEDEV_OT_export_rigged(bpy.types.Operator):
    bl_idname = "nmggamedev.export_rigged"
    bl_label = "Export rigged character"
    bl_description = (
        "Write SM_<Name>.fbx with the deform skeleton and baked clips, the material PNGs, and "
        "nmg-animations.json"
    )
    bl_options = {"REGISTER", "UNDO"}

    collection_name: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Asset collection",
        description="Collection <Name> whose rig is SK_<Name>",
        default="",
    )
    out_dir: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Output folder",
        description="Folder that receives the FBX, PNGs, and nmg-animations.json",
        subtype="DIR_PATH",
        default="",
    )

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context) -> set[str]:
        result = write_rigged(self.collection_name, self.out_dir)
        store_rig_result(context, result)
        if result["status"] == "ok":
            log_operator_result(_OP_NAME, f"{self.collection_name}: exported {result['fbx']}")
            return {"FINISHED"}
        self.report(
            {"ERROR"},
            f"{result['code']}: {result['message']} — {result['remediation']}",
        )
        return {"CANCELLED"}
