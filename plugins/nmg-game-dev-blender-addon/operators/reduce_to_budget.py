from __future__ import annotations

import bpy

from ..reduce_core import ReduceError, reduce_asset
from ..utils.logging import log_operator_result
from ._common import ASSET_CLASS_ITEMS, store_last_result

_OP_NAME = "nmggamedev.reduce_to_budget"


class NMGGAMEDEV_OT_reduce_to_budget(bpy.types.Operator):
    bl_idname = "nmggamedev.reduce_to_budget"
    bl_label = "Reduce to Desktop budget"
    bl_description = (
        "Reduce a generated high-poly collection to its Desktop triangle budget, keep the "
        "originals in a hidden <Name>_High, and bake their look onto the reduced mesh"
    )
    bl_options = {"REGISTER", "UNDO"}

    collection_name: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Asset collection",
        description="Collection <Name> whose meshes are the high-poly parts to reduce",
        default="",
    )
    asset_class: bpy.props.EnumProperty(  # type: ignore[valid-type]
        name="Asset class",
        description="Contract section 6 class whose Desktop budget applies",
        items=ASSET_CLASS_ITEMS,
        default="standard_prop",
    )
    budgets_path: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Budget overrides",
        description="Optional nmg-budgets.json with Desktop overrides",
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
    cage_extrusion: bpy.props.FloatProperty(  # type: ignore[valid-type]
        name="Cage extrusion (m)",
        description="Ray start offset for the bake, applied to every part",
        default=0.03,
        min=0.0001,
        precision=4,
    )
    max_ray_distance: bpy.props.FloatProperty(  # type: ignore[valid-type]
        name="Max ray distance (m)",
        description="Farthest distance a bake ray may travel to reach the original",
        default=0.10,
        min=0.0001,
        precision=4,
    )
    miss_threshold: bpy.props.FloatProperty(  # type: ignore[valid-type]
        name="Miss threshold",
        description="Largest unbaked share of a part's texels before the reduce fails",
        default=0.01,
        min=0.0,
        max=1.0,
        precision=3,
    )

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context) -> set[str]:
        if not self.collection_name:
            self.report({"ERROR"}, "reduce.collection_missing: set the asset collection first")
            return {"CANCELLED"}
        try:
            result = reduce_asset(
                self.collection_name,
                self.asset_class,
                self.budgets_path or None,
                device=self.device,
                cage_extrusion=self.cage_extrusion,
                max_ray_distance=self.max_ray_distance,
                miss_threshold=self.miss_threshold,
            )
        except ReduceError as error:
            self.report(
                {"ERROR"},
                f"{error.code}: {error.message} — {error.remediation}",
            )
            return {"CANCELLED"}
        store_last_result(context, result)
        log_operator_result(_OP_NAME, result["summary"])
        return {"FINISHED"}
