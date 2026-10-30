from __future__ import annotations

import json
from pathlib import Path

import bpy

from ..contract_core import ContractError, validate_asset
from ..utils.logging import log_operator_result
from ._common import ASSET_CLASS_ITEMS, store_last_result

_OP_NAME = "nmggamedev.validate_contract"


class NMGGAMEDEV_OT_validate_contract(bpy.types.Operator):
    bl_idname = "nmggamedev.validate_contract"
    bl_label = "Validate asset contract"
    bl_description = "Check the asset collection against asset-contract sections 1-6"
    bl_options = {"REGISTER", "UNDO"}

    collection_name: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Asset collection",
        description="Collection <Name> that holds the root mesh SM_<Name>",
        default="",
    )
    asset_class: bpy.props.EnumProperty(  # type: ignore[valid-type]
        name="Asset class",
        description="Contract section 6 class whose budgets apply",
        items=ASSET_CLASS_ITEMS,
        default="standard_prop",
    )
    budgets_path: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Budget overrides",
        description="Optional nmg-budgets.json with Mobile overrides",
        subtype="FILE_PATH",
        default="",
    )
    report_path: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Report file",
        description="Optional JSON file that receives the contract report",
        subtype="FILE_PATH",
        default="",
    )

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            report = validate_asset(self.collection_name, self.asset_class, self.budgets_path)
        except ContractError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        store_last_result(context, report)
        if self.report_path:
            _write_report(Path(self.report_path), report)
        if report["passed"]:
            log_operator_result(_OP_NAME, f"{self.collection_name}: contract passed")
            return {"FINISHED"}
        rules = sorted({item["rule"] for item in report["findings"]})
        self.report(
            {"ERROR"},
            f"{self.collection_name} fails {len(report['findings'])} contract check(s): "
            + ", ".join(rules),
        )
        return {"CANCELLED"}


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
