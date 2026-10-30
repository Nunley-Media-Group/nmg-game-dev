from __future__ import annotations

import bpy

from ..utils.logging import log_operator_result
from ..variants_core import VariantError, generate_variants
from ._common import ASSET_CLASS_ITEMS, store_last_result

_OP_NAME = "nmggamedev.generate_variants"


class NMGGAMEDEV_OT_generate_variants(bpy.types.Operator):
    bl_idname = "nmggamedev.generate_variants"
    bl_label = "Generate Desktop + Mobile variants"
    bl_description = "Clean up, build Mobile LODs, export both FBX variants, and write sidecars"
    bl_options = {"REGISTER", "UNDO"}

    collection_name: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Asset collection",
        description="Collection <Name> that holds the root mesh SM_<Name>",
        default="",
    )
    category: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Category",
        description="PascalCase export category, e.g. Props",
        default="",
    )
    asset_class: bpy.props.EnumProperty(  # type: ignore[valid-type]
        name="Asset class",
        description="Contract section 6 class whose budgets apply",
        items=ASSET_CLASS_ITEMS,
        default="standard_prop",
    )
    export_root: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Export root",
        description="Directory that receives <Category>/<Name>/Desktop and Mobile",
        subtype="DIR_PATH",
        default="",
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
            result = generate_variants(
                self.collection_name,
                self.category,
                self.asset_class,
                self.export_root,
                self.budgets_path,
            )
        except VariantError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        store_last_result(context, result)
        log_operator_result(
            _OP_NAME,
            f"Desktop {result['poly_count_desktop']} triangles, "
            f"Mobile {result['poly_count_mobile']} triangles, "
            f"exported to {result['desktop_path']}",
        )
        return {"FINISHED"}
