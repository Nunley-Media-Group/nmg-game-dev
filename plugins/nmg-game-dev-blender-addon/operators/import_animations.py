from __future__ import annotations

import bpy

from ..rig_core import import_animations as bake_animations
from ..utils.logging import log_operator_result
from ._common import store_rig_result

_OP_NAME = "nmggamedev.import_animations"


class NMGGAMEDEV_OT_import_animations(bpy.types.Operator):
    bl_idname = "nmggamedev.import_animations"
    bl_label = "Import animation library clips"
    bl_description = (
        "Retarget clips from a local animation library onto SK_<Name> and bake them as actions"
    )
    bl_options = {"REGISTER", "UNDO"}

    collection_name: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Asset collection",
        description="Collection <Name> whose rig is SK_<Name>",
        default="",
    )
    library_dir: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Animation library",
        description="Folder that holds library.json and its FBX or BVH clips",
        subtype="DIR_PATH",
        default="",
    )
    clips: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Clips",
        description="Comma-separated clip names to import; empty imports every clip",
        default="",
    )
    motion_prompt: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Motion prompt",
        description="Text-driven motion is reported as unsupported; leave empty",
        default="",
    )

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context) -> set[str]:
        names = [name.strip() for name in self.clips.split(",") if name.strip()]
        result = bake_animations(
            self.collection_name, self.library_dir, names or None, self.motion_prompt or None
        )
        store_rig_result(context, result)
        if result["status"] == "ok":
            log_operator_result(_OP_NAME, f"{self.collection_name}: {len(result['clips'])} clip(s)")
            return {"FINISHED"}
        self.report(
            {"ERROR"},
            f"{result['code']}: {result['message']} — {result['remediation']}",
        )
        return {"CANCELLED"}
