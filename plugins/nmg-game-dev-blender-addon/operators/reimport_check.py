from __future__ import annotations

import bpy

from ..contract_core import ContractError, run_isolated
from ..utils.logging import log_operator_result
from ._common import store_last_result

_OP_NAME = "nmggamedev.reimport_check"


class NMGGAMEDEV_OT_reimport_check(bpy.types.Operator):
    bl_idname = "nmggamedev.reimport_check"
    bl_label = "Re-import check"
    bl_description = "Import the exported FBX in a fresh Blender and compare it with the report"
    bl_options = {"REGISTER"}

    variant_dir: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Variant folder",
        description="Exported <Category>/<Name>/Desktop or Mobile folder",
        subtype="DIR_PATH",
        default="",
    )
    pre_report_path: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Pre-export report",
        description="Contract report written before export (validate_contract)",
        subtype="FILE_PATH",
        default="",
    )
    report_path: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Report file",
        description="Optional JSON file that receives the re-import report",
        subtype="FILE_PATH",
        default="",
    )

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            report = run_isolated(
                self.variant_dir,
                self.pre_report_path,
                report_path=self.report_path or None,
            )
        except ContractError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        store_last_result(context, report)
        if report["passed"]:
            log_operator_result(_OP_NAME, f"{report['asset']}: re-import matches the report")
            return {"FINISHED"}
        rules = sorted({item["rule"] for item in report["findings"]})
        self.report(
            {"ERROR"},
            f"Re-import of {report['asset']} fails: " + ", ".join(rules),
        )
        return {"CANCELLED"}
