"""Finding and report builders for the contract checks, plus the rule catalogue.

A report is plain JSON, so the Blender side and the host-side gate share one schema without
importing each other (design § Data / Storage Changes).
"""

from __future__ import annotations

from typing import Any, Final

RULES: Final[dict[str, str]] = {
    "scene.collection": (
        "Move lights, cameras, and set dressing into <Name>_Preview; the asset collection holds "
        "only shipping meshes and empties (contract section 1)."
    ),
    "scene.units": "Set Scene > Units to Metric with Unit Scale 1.0 (contract section 2).",
    "naming.root": "Name the root SM_<Name> (Mobile: SM_<Name>_Mobile), contract section 1.",
    "naming.part": "Name child parts SM_<Name>_<Part> and parent each one to the root (section 1).",
    "naming.material": "Name each material M_<Name>_<Part> (contract section 4).",
    "naming.texture": "Name each image T_<Name>_<Part>_BC, _N, or _ORM (contract section 4).",
    "transform.root_applied": (
        "Apply the root transform (Ctrl+A > All Transforms) so location, rotation, and scale are "
        "identity (contract section 2)."
    ),
    "transform.part_applied": (
        "Clear the child part's rotation and set its scale to 1; keep its pivot in the origin "
        "(contract section 2)."
    ),
    "pivot.bottom_center": (
        "Set the origin to the bottom center of the asset and place it at the world origin "
        "(contract section 2)."
    ),
    "geometry.loose": "Delete loose vertices and edges (Mesh > Clean Up > Delete Loose).",
    "geometry.zero_area": "Delete zero-area faces (Mesh > Clean Up > Degenerate Dissolve).",
    "geometry.duplicates": "Merge duplicate vertices (Mesh > Clean Up > Merge by Distance).",
    "geometry.normals": "Recalculate normals outside (Shift+N) so every face points outward.",
    "uv.single_map": "Keep exactly one UV map on every mesh, named UVMap (contract section 4).",
    "uv.overlap": (
        "Unwrap so UV islands do not overlap; environment pieces use the tiling mode instead "
        "(contract section 4)."
    ),
    "material.node_types": (
        "Bake the material to images and feed the Principled BSDF only from Image Texture, "
        "Normal Map, and Separate Color nodes (contract section 4)."
    ),
    "material.uv_coordinates": (
        "Sample every Image Texture through a UV Map node set to UVMap; remove Generated, "
        "Object, and Position coordinates (contract section 4)."
    ),
    "texture.power_of_two": "Resize the image to a power-of-two square, such as 512 or 1024.",
    "budget.tris": (
        "Reduce triangles to the class budget in contract section 6, or set a justified override "
        "in nmg-budgets.json."
    ),
    "budget.materials": "Merge materials to the class material limit (contract section 6).",
    "budget.texture_size": "Resize textures to the class maximum (contract section 6).",
    "texel.density": (
        "Raise texel density to 256 px/m (Desktop) or 128 px/m (Mobile) with more texture "
        "resolution or less UV area per meter (contract section 6)."
    ),
    "variants.names_match": (
        "Give each Mobile object, material, and image the Desktop name plus the _Mobile suffix; "
        "LOD objects add _LOD0 to _LOD2 (contract section 5)."
    ),
    "reimport.texture_missing": "Re-export so each BC and N PNG sits beside the FBX (section 7).",
    "reimport.orm_missing": "Re-export so the ORM PNG sits beside the FBX (section 7).",
    "reimport.uv_missing": "Re-export with UVMap present on every mesh (contract section 4).",
    "reimport.name_mismatch": "Re-export so object and material names match the pre-export report.",
    "reimport.dimensions": "Re-export without changing scale or geometry, then validate again.",
    "reimport.pivot": "Re-export with child-part pivots unchanged from the pre-export report.",
    "reimport.tris": "Re-export with the same triangle count as the pre-export report.",
}


class ContractError(Exception):
    """A contract step that must stop, carrying the code, message, and remediation to report."""

    def __init__(self, code: str, message: str, remediation: str) -> None:
        super().__init__(f"{code}: {message} — {remediation}")
        self.code = code
        self.message = message
        self.remediation = remediation


def finding(rule: str, target: str, message: str) -> dict[str, str]:
    """One violated rule, with the catalogue's remediation for that rule."""
    return {"rule": rule, "target": target, "message": message, "remediation": RULES[rule]}


def build_report(
    kind: str,
    asset: str,
    asset_class: str,
    findings: list[dict[str, str]],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the shared report shape; passed is true exactly when there are no findings."""
    return {
        "kind": kind,
        "asset": asset,
        "class": asset_class,
        "passed": not findings,
        "findings": findings,
        "snapshot": snapshot,
    }
