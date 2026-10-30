from __future__ import annotations

import bpy

from ..bake_core import BakeError, bake_asset
from ..utils.logging import log_operator_result
from ._common import ASSET_CLASS_ITEMS, store_last_result

_OP_NAME = "nmggamedev.bake_materials"


class NMGGAMEDEV_OT_bake_materials(bpy.types.Operator):
    bl_idname = "nmggamedev.bake_materials"
    bl_label = "Bake materials to contract textures"
    bl_description = (
        "Bake the collection's authored materials to BC / N / ORM texture sets at Desktop and "
        "Mobile size, rewire the materials to them, and proof the result against a pre-bake render"
    )
    bl_options = {"REGISTER", "UNDO"}

    collection_name: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Asset collection",
        description="Collection <Name> whose meshes hold the authored materials",
        default="",
    )
    asset_class: bpy.props.EnumProperty(  # type: ignore[valid-type]
        name="Asset class",
        description="Contract section 6 class whose texture sizes and material limits apply",
        items=ASSET_CLASS_ITEMS,
        default="standard_prop",
    )
    out_dir: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Output folder",
        description="Folder that receives Desktop/, Mobile/, the proof renders, and bake.json",
        subtype="DIR_PATH",
        default="",
    )
    budgets_path: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Budget overrides",
        description="Optional nmg-budgets.json with Desktop and Mobile overrides",
        subtype="FILE_PATH",
        default="",
    )
    device: bpy.props.EnumProperty(  # type: ignore[valid-type]
        name="Device",
        description="Cycles device for the bake; CPU is used when no GPU device is available",
        items=(
            ("GPU", "GPU", "Use the GPU when Cycles reports one"),
            ("CPU", "CPU", "Always bake on the CPU"),
        ),
        default="GPU",
    )
    samples: bpy.props.IntProperty(  # type: ignore[valid-type]
        name="Samples",
        description="Cycles samples per bake pass",
        default=32,
        min=1,
    )

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context) -> set[str]:
        if not self.out_dir:
            self.report({"ERROR"}, "texture.bake_failed: set an output folder before baking")
            return {"CANCELLED"}
        try:
            result = bake_asset(
                self.collection_name,
                self.asset_class,
                self.out_dir,
                self.budgets_path or None,
                self.device,
                self.samples,
            )
        except BakeError as error:
            self.report(
                {"ERROR"},
                f"{error.code}: {error.message} — {error.remediation}",
            )
            return {"CANCELLED"}
        store_last_result(context, result)
        log_operator_result(_OP_NAME, result["summary"])
        return {"FINISHED"}
