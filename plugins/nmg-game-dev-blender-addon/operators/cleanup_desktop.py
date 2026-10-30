from __future__ import annotations

import bpy

from ..utils.logging import log_operator_result
from ..variants_core import VariantError, cleanup_desktop
from ._common import store_last_result

_OP_NAME = "nmggamedev.cleanup_desktop"


class NMGGAMEDEV_OT_cleanup_desktop(bpy.types.Operator):
    bl_idname = "nmggamedev.cleanup_desktop"
    bl_label = "Clean up for Desktop variant"
    bl_description = "Apply modifiers and remove duplicate, loose, and zero-area geometry"
    bl_options = {"REGISTER", "UNDO"}

    collection_name: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Asset collection",
        description="Collection <Name> that holds the root mesh SM_<Name>",
        default="",
    )

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            result = cleanup_desktop(self.collection_name)
        except VariantError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        store_last_result(context, result)
        log_operator_result(
            _OP_NAME, f"triangles {result['tris_before']} -> {result['tris_after']}"
        )
        return {"FINISHED"}
