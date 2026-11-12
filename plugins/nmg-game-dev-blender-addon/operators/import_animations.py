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
        "Bake clips from a local animation library, or the built-in procedural library, onto "
        "SK_<Name> as actions"
    )
    bl_options = {"REGISTER", "UNDO"}

    collection_name: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Asset collection",
        description="Collection <Name> whose rig is SK_<Name>",
        default="",
    )
    library_source: bpy.props.EnumProperty(  # type: ignore[valid-type]
        name="Library",
        description="Bake from a folder of clips, or from the built-in procedural library",
        items=(
            ("FOLDER", "Animation folder", "Clips in the library folder below"),
            ("BUILTIN", "Built-in library", "Procedural clips shipped with the add-on"),
        ),
        default="FOLDER",
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
        prompt = self.motion_prompt or None
        if self.library_source == "BUILTIN":
            result = bake_animations(
                self.collection_name, None, names or None, prompt, library="builtin"
            )
        else:
            result = bake_animations(self.collection_name, self.library_dir, names or None, prompt)
        store_rig_result(context, result)
        if result["status"] == "ok":
            log_operator_result(_OP_NAME, f"{self.collection_name}: {len(result['clips'])} clip(s)")
            return {"FINISHED"}
        self.report(
            {"ERROR"},
            f"{result['code']}: {result['message']} — {result['remediation']}",
        )
        return {"CANCELLED"}
