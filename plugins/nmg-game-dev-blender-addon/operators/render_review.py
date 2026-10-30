from __future__ import annotations

import bpy

from ..contract_core import ContractError, render_review, render_texture_proof
from ..utils.logging import log_operator_result
from ._common import store_last_result

_OP_NAME = "nmggamedev.render_review"


class NMGGAMEDEV_OT_render_review(bpy.types.Operator):
    bl_idname = "nmggamedev.render_review"
    bl_label = "Render review images"
    bl_description = "Render front, back, side, and three-quarter views, and the texture proof"
    bl_options = {"REGISTER"}

    collection_name: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Asset collection",
        description="Collection <Name> to render; <Name>_Mobile is rendered when present",
        default="",
    )
    out_dir: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Output folder",
        description="Folder that receives <variant>/<Name>_<view>.png",
        subtype="DIR_PATH",
        default="",
    )
    resolution: bpy.props.IntProperty(  # type: ignore[valid-type]
        name="Resolution",
        description="Square render size in pixels",
        default=1024,
        min=16,
        max=4096,
    )
    proof_variant_dir: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Exported variant folder",
        description="Optional exported Desktop or Mobile folder for the texture proof",
        subtype="DIR_PATH",
        default="",
    )
    pre_bake_path: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Pre-bake render",
        description="Optional render made before baking, shown in the proof sheet",
        subtype="FILE_PATH",
        default="",
    )

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            result = render_review(self.collection_name, self.out_dir, self.resolution)
            if self.proof_variant_dir:
                proof = render_texture_proof(
                    self.proof_variant_dir,
                    self.out_dir,
                    pre_bake=self.pre_bake_path or None,
                    collection=self.collection_name,
                    resolution=self.resolution,
                )
                result["proof"] = proof["proof"]
        except ContractError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        store_last_result(context, result)
        log_operator_result(_OP_NAME, f"wrote {len(result['files'])} review image(s)")
        return {"FINISHED"}
