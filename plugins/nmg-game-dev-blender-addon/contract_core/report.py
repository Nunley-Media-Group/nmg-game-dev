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
    "geometry.normals": (
        "Closed parts: recalculate normals outside (Shift+N) on that part only, so every face "
        "points outward. Open sheets such as floors, roof planes, and decals: do not recalculate "
        "outside; flip only the faces wound opposite to their neighbours (Mesh > Normals > Flip), "
        "so the sheet is wound consistently and faces the viewer."
    ),
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
        "Density is checked per material slot. Raise the slot to 256 px/m (Desktop) or 128 px/m "
        "(Mobile) with more texture resolution or less UV area per meter, or set the custom "
        "property nmg_trim_atlas to True on the material if it is a trim atlas (contract "
        "section 6)."
    ),
    "variants.names_match": (
        "Give each Mobile object, material, and image the Desktop name plus the _Mobile suffix; "
        "LOD objects add _LOD0 to _LOD2 (contract section 5)."
    ),
    "material_variant.name": (
        "Name each material variant in PascalCase letters and digits, and pick a name so that "
        "<Part>_<Variant> is not another part's name (contract section 4)."
    ),
    "material_variant.duplicate": (
        "Give each material variant on one material a different name (contract section 4)."
    ),
    "material_variant.material_missing": (
        "Declare the variant on a material the asset has after the bake, M_<Name>_<Part> "
        "(contract section 4)."
    ),
    "material_variant.material_merged": (
        "The bake merges these authored materials into M_<Name>_Body; declare the variant on "
        "M_<Name>_Body instead (contract section 4)."
    ),
    "material_variant.texture_missing": (
        "Point base_color at an existing PNG file beside the declaration (contract section 4)."
    ),
    "material_variant.texture_size": (
        "Make the replacement base colour a power-of-two square the size of the Desktop base "
        "colour of its material (contract section 4)."
    ),
    "material_variant.parameter": (
        "Use a parameter M_NmgORM declares (Tint), with [r, g, b] or [r, g, b, a] finite numbers "
        "of at least 0 (contract section 4)."
    ),
    "material_variant.empty": (
        "Give the material variant a base_color, parameters, or both (contract section 4)."
    ),
    "material_variant.declaration_invalid": (
        "Fix <Name>.material-variants.json to the format in contract section 4 (raised as an "
        "error, not a finding)."
    ),
    "reimport.texture_missing": "Re-export so each BC and N PNG sits beside the FBX (section 7).",
    "reimport.orm_missing": "Re-export so the ORM PNG sits beside the FBX (section 7).",
    "reimport.uv_missing": "Re-export with UVMap present on every mesh (contract section 4).",
    "reimport.name_mismatch": "Re-export so object and material names match the pre-export report.",
    "reimport.dimensions": "Re-export without changing scale or geometry, then validate again.",
    "reimport.pivot": "Re-export with child-part pivots unchanged from the pre-export report.",
    "reimport.tris": "Re-export with the same triangle count as the pre-export report.",
    "reimport.skin_missing": (
        "Re-export the rigged variant with the armature and its skin: every mesh needs an "
        "Armature modifier or armature parent, and vertex groups (#102)."
    ),
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
