from __future__ import annotations

import bpy

from ..utils.logging import log_operator_result
from ..variants_core import VariantError, optimize_mobile
from ._common import ASSET_CLASS_ITEMS, store_last_result

_OP_NAME = "nmggamedev.optimize_mobile"


class NMGGAMEDEV_OT_optimize_mobile(bpy.types.Operator):
    bl_idname = "nmggamedev.optimize_mobile"
    bl_label = "Optimize for Mobile variant"
    bl_description = "Rebuild <Name>_Mobile: decimate to budget with LOD1 and LOD2"
    bl_options = {"REGISTER", "UNDO"}

    collection_name: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Asset collection",
        description="Collection <Name> that holds the root mesh SM_<Name>",
        default="",
    )
    asset_class: bpy.props.EnumProperty(  # type: ignore[valid-type]
        name="Asset class",
        description="Contract section 6 class whose Mobile budget applies",
        items=ASSET_CLASS_ITEMS,
        default="standard_prop",
    )
    budgets_path: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Budget overrides",
        description="Optional nmg-budgets.json with Mobile overrides",
        subtype="FILE_PATH",
        default="",
    )

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            result = optimize_mobile(self.collection_name, self.asset_class, self.budgets_path)
        except VariantError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        store_last_result(context, result)
        log_operator_result(
            _OP_NAME,
            f"LOD0 {result['tris']} triangles, {result['lod_levels']} LOD level(s)",
        )
        return {"FINISHED"}
