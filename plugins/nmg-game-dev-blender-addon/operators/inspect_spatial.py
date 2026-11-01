from __future__ import annotations

import bpy

from ..contract_core import ContractError
from ..inspect_core import DEFAULT_GAP_TOLERANCE, inspect_asset
from ..utils.logging import log_operator_result
from ._common import ASSET_CLASS_ITEMS, store_last_result

_OP_NAME = "nmggamedev.inspect_spatial"


class NMGGAMEDEV_OT_inspect_spatial(bpy.types.Operator):
    bl_idname = "nmggamedev.inspect_spatial"
    bl_label = "Inspect spatial rules"
    bl_description = (
        "Report floating parts, interpenetration, non-manifold edges, and triangle headroom"
    )
    bl_options = {"REGISTER"}

    collection_name: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Asset collection",
        description="Collection <Name> whose mesh parts are inspected",
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
        description="Optional nmg-budgets.json with class overrides",
        subtype="FILE_PATH",
        default="",
    )
    gap_tolerance: bpy.props.FloatProperty(  # type: ignore[valid-type]
        name="Gap tolerance",
        description="Metres within which two parts count as touching",
        default=DEFAULT_GAP_TOLERANCE,
        min=0.0,
    )

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            report = inspect_asset(
                self.collection_name,
                self.asset_class,
                self.budgets_path or None,
                gap_tolerance=self.gap_tolerance,
            )
        except ContractError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        store_last_result(context, report)
        verdict = "passed" if report["passed"] else "failed"
        log_operator_result(_OP_NAME, f"{verdict} with {len(report['findings'])} finding(s)")
        return {"FINISHED"}
