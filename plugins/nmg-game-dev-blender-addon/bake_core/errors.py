"""BakeError: the single error the bake raises, with a code, reason, message, and remediation."""

from __future__ import annotations

from typing import Final

BAKE_ERROR_CODE: Final = "texture.bake_failed"

# Reason -> default remediation. Every BakeError names one of these reasons.
REASONS: Final[dict[str, str]] = {
    "collection_missing": "Open the file that holds the asset, or pass its collection name.",
    "no_mesh": "Add mesh objects to the asset collection, then rerun the bake.",
    "budget_invalid": "Use a listed asset class and power-of-two sizes in nmg-budgets.json.",
    "no_material": "Give every mesh a material in every slot, then rerun the bake.",
    "unsupported_shader": "Replace the node with a Principled BSDF, Mix Shader, or Add Shader.",
    "transparency": "Set Alpha to 1 and Transmission Weight to 0, then rerun the bake.",
    "emission": "Set Emission Strength to 0 or Emission Color to black, then rerun the bake.",
    "volume_or_displacement": "Unlink the Volume and Displacement outputs before baking.",
    "uv_missing": "Give every mesh at least one UV map before baking a tiling asset.",
    "uv_unwrap_failed": "Check that the mesh has faces with area, then rerun the bake.",
    "not_seamless": "Make the tiling material periodic across 0 to 1 UV, then rerun the bake.",
    "texel_density": "Increase the UV scale or the mesh area ratio until the density is met.",
    "material_limit": "Reduce the tiling materials to the class limit, then rerun the bake.",
    "proof_mismatch": "The baked render differs from the pre-bake render. Check the seams, color "
    "space, and roughness in the proof renders, fix the material, then rebake.",
    "internal_error": "Check the Blender log for the traceback, fix the cause, and rerun.",
}


class BakeError(Exception):
    """A bake step that must stop, carrying the code, reason, message, and remediation."""

    def __init__(
        self,
        reason: str,
        message: str,
        *,
        target: str = "",
        remediation: str | None = None,
    ) -> None:
        self.code = BAKE_ERROR_CODE
        self.reason = reason
        self.message = message
        self.target = target
        self.remediation = remediation or REASONS.get(reason, REASONS["internal_error"])
        super().__init__(f"{self.code} [{reason}]: {message} — {self.remediation}")

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "remediation": self.remediation,
            "target": self.target,
            "reason": self.reason,
        }
