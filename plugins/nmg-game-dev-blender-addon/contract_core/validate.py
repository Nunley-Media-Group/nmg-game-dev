"""Contract validation for one asset collection and its <Name>_Mobile sibling.

validate_asset implements sections 1-6 of docs/asset-contract.md. Mesh checks run on evaluated
copies that are removed before returning, so the scene is never changed.
"""

from __future__ import annotations

import math
import re
from typing import Any

import bpy
from mathutils import Vector

from ..utils.budgets import CONTRACT_BUDGETS, BudgetOverrideError, resolve_budget
from .geometry import geometry_findings
from .report import ContractError, build_report, finding
from .uv import uv_findings

LOCATION_TOLERANCE = 1e-5
ANGLE_TOLERANCE = 1e-5
PIVOT_TOLERANCE = 1e-3
TEXEL_DENSITY_MIN: dict[str, float] = {"desktop": 256.0, "mobile": 128.0}
ALLOWED_NODE_TYPES = frozenset(
    {
        "TEX_IMAGE",
        "NORMAL_MAP",
        "SEPARATE_COLOR",
        "BSDF_PRINCIPLED",
        "OUTPUT_MATERIAL",
        # UV Map sources the Image Texture vector, and reroutes are plumbing; the variants
        # bake check (variants_core/textures.py) allows the same two nodes.
        "UVMAP",
        "REROUTE",
    }
)
MOBILE_SUFFIX = "_Mobile"
_UV_MAP = "UVMap"
_LOD_EXTRA = re.compile(r"_LOD[1-9]$")
_LOD_ANY = re.compile(r"_LOD\d+$")


# Rules that only a baked asset can satisfy (section 4 materials and their texture sets).
# An authored asset is validated without them, and the export gate enforces them after the bake.
_EXPORT_ONLY_RULES: tuple[str, ...] = (
    "material.",
    "naming.material",
    "naming.texture",
    "texture.",
    "budget.texture_size",
    "budget.materials",
)


def validate_asset(
    collection: str,
    asset_class: str,
    budgets_path: str | None = None,
    *,
    authored: bool = False,
) -> dict[str, Any]:
    """Validate <collection> (Desktop) and <collection>_Mobile when it exists.

    With ``authored=True`` (the finalize validate step, #69), material and texture rules are
    skipped, because the bake step produces them. The export gate runs the full contract.
    """
    budgets = _budgets(asset_class, budgets_path)
    bpy.context.view_layer.update()
    asset = bpy.data.collections.get(collection)
    if asset is None:
        missing = finding(
            "scene.collection", collection, f"No collection named '{collection}' is in the file."
        )
        return build_report("contract", collection, asset_class, [missing], {})

    variants: list[tuple[str, bpy.types.Collection]] = [("desktop", asset)]
    mobile = bpy.data.collections.get(f"{collection}{MOBILE_SUFFIX}")
    if mobile is not None:
        variants.append(("mobile", mobile))

    findings = _unit_findings()
    snapshot: dict[str, Any] = {}
    objects_by_variant: dict[str, list[bpy.types.Object]] = {}
    for variant, variant_collection in variants:
        root_name = _root_name(collection, variant)
        objects = sorted(variant_collection.all_objects, key=lambda obj: obj.name)
        objects_by_variant[variant] = objects
        tris: dict[str, int] = {}
        findings += _structure_findings(collection, variant, objects, root_name)
        findings += _mesh_findings(
            collection, variant, asset_class, objects, budgets[variant], root_name, tris
        )
        for obj in objects:
            snapshot[obj.name] = object_snapshot(obj, variant, tris.get(obj.name, 0))
    if mobile is not None:
        findings += _variant_name_findings(
            objects_by_variant["desktop"], objects_by_variant["mobile"]
        )
    if authored:
        findings = [item for item in findings if not item["rule"].startswith(_EXPORT_ONLY_RULES)]
    return build_report("contract", collection, asset_class, findings, snapshot)


def triangle_count(mesh: bpy.types.Mesh) -> int:
    return sum(max(poly.loop_total - 2, 0) for poly in mesh.polygons)


def export_name(name: str) -> str:
    """The name an object, material, or image carries in the exported FBX and PNG files.

    Matches variants_core/export.py: only the Mobile suffix is removed.
    """
    return name.replace(MOBILE_SUFFIX, "", 1)


def _variant_key(name: str) -> str:
    """Desktop name that a Mobile object (possibly an LOD0-2 child) stands for."""
    return export_name(_LOD_ANY.sub("", name))


def object_snapshot(obj: bpy.types.Object, variant: str, tris: int) -> dict[str, Any]:
    is_mesh = obj.type == "MESH"
    return {
        "variant": variant,
        "type": obj.type,
        "parent": obj.parent.name if obj.parent is not None else None,
        "tris": tris,
        "dimensions": _rounded(obj.dimensions),
        "location": _rounded(obj.location),
        "rotation": _rounded(obj.rotation_euler),
        "scale": _rounded(obj.scale),
        "origin": _rounded(obj.matrix_world.translation),
        "local_bounds": _local_bounds(obj) if is_mesh else None,
        "uv_maps": [layer.name for layer in obj.data.uv_layers] if is_mesh else [],
        "materials": sorted({material.name for material in _materials_of(obj)}),
        "images": sorted(
            {image.name for material in _materials_of(obj) for image in _images_of(material)}
        ),
    }


def _budgets(asset_class: str, budgets_path: str | None) -> dict[str, dict[str, int]]:
    try:
        mobile = resolve_budget(asset_class, budgets_path or None)
    except BudgetOverrideError as error:
        raise ContractError(error.code, error.message, error.remediation) from error
    return {"desktop": dict(CONTRACT_BUDGETS[asset_class]["desktop"]), "mobile": mobile}


def _root_name(collection: str, variant: str) -> str:
    return f"SM_{collection}" if variant == "desktop" else f"SM_{collection}{MOBILE_SUFFIX}"


def _unit_findings() -> list[dict[str, str]]:
    units = bpy.context.scene.unit_settings
    if units.system == "METRIC" and abs(units.scale_length - 1.0) <= 1e-6:
        return []
    return [
        finding(
            "scene.units",
            bpy.context.scene.name,
            f"Scene units are {units.system.title()} at scale {units.scale_length:g}; "
            "contract section 2 needs Metric at 1.0.",
        )
    ]


def _structure_findings(
    collection: str, variant: str, objects: list[bpy.types.Object], root_name: str
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for obj in objects:
        if obj.type in {"LIGHT", "CAMERA"}:
            findings.append(
                finding(
                    "scene.collection",
                    obj.name,
                    f"{obj.name} is a {obj.type.lower()} in the {variant} asset collection; "
                    f"move it to {collection}_Preview.",
                )
            )

    root = next((obj for obj in objects if obj.name == root_name), None)
    if root is None or (variant == "desktop" and root.type != "MESH"):
        findings.append(
            finding(
                "naming.root",
                root_name,
                f"The {variant} collection has no root object named {root_name}.",
            )
        )
        return findings

    problems = _basis_problems(root, check_location=True)
    if problems:
        findings.append(
            finding(
                "transform.root_applied",
                root.name,
                f"{root.name} is not in identity: {', '.join(problems)}.",
            )
        )
    meshes = [obj for obj in objects if obj.type == "MESH" and not _LOD_EXTRA.search(obj.name)]
    findings += _pivot_findings(root, meshes)

    for obj in objects:
        if obj.type != "MESH" or obj.name == root_name or _LOD_ANY.search(obj.name):
            continue
        if variant == "desktop" and not re.fullmatch(
            rf"SM_{re.escape(collection)}_[A-Za-z0-9]+", obj.name
        ):
            findings.append(
                finding(
                    "naming.part",
                    obj.name,
                    f"{obj.name} is not named SM_{collection}_<Part>.",
                )
            )
        if obj.parent is not root:
            findings.append(
                finding("naming.part", obj.name, f"{obj.name} is not parented to {root_name}.")
            )
        problems = _basis_problems(obj, check_location=False)
        if problems:
            findings.append(
                finding(
                    "transform.part_applied",
                    obj.name,
                    f"{obj.name} has rotation or scale on the part: {', '.join(problems)}.",
                )
            )
    return findings


def _basis_problems(obj: bpy.types.Object, check_location: bool) -> list[str]:
    location, rotation, scale = obj.matrix_basis.decompose()
    problems: list[str] = []
    if check_location and not _close(location, (0.0, 0.0, 0.0), LOCATION_TOLERANCE):
        problems.append(f"location {_format(location)}")
    if rotation.angle > ANGLE_TOLERANCE:
        problems.append(f"rotation {math.degrees(rotation.angle):.3f} deg")
    if not _close(scale, (1.0, 1.0, 1.0), LOCATION_TOLERANCE):
        problems.append(f"scale {_format(scale)}")
    return problems


def _pivot_findings(root: bpy.types.Object, meshes: list[bpy.types.Object]) -> list[dict[str, str]]:
    if not meshes:
        return []
    origin = root.matrix_world.translation
    corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    xs = [corner.x for corner in corners]
    ys = [corner.y for corner in corners]
    zs = [corner.z for corner in corners]
    bottom_z = min(zs)
    center_x = (min(xs) + max(xs)) / 2
    center_y = (min(ys) + max(ys)) / 2
    checked = (origin.x, origin.y, origin.z, bottom_z, center_x, center_y)
    if all(abs(value) <= PIVOT_TOLERANCE for value in checked):
        return []
    return [
        finding(
            "pivot.bottom_center",
            root.name,
            f"{root.name} origin is at ({origin.x:.4f}, {origin.y:.4f}, {origin.z:.4f}) and the "
            f"bottom center is at ({center_x:.4f}, {center_y:.4f}, {bottom_z:.4f}); both must be "
            "at the world origin.",
        )
    ]


def _mesh_findings(
    collection: str,
    variant: str,
    asset_class: str,
    objects: list[bpy.types.Object],
    budget: dict[str, int],
    root_name: str,
    tris_out: dict[str, int],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    meshes = [obj for obj in objects if obj.type == "MESH"]
    texel_check = asset_class == "environment_piece"
    materials: dict[str, bpy.types.Material] = {}
    images: dict[str, bpy.types.Image] = {}
    for obj in meshes:
        copy = _evaluated_copy(obj)
        try:
            tris_out[obj.name] = triangle_count(copy)
            findings += geometry_findings(obj.name, copy)
            findings += uv_findings(obj.name, copy, check_overlap=not texel_check)
            if texel_check:
                findings += _texel_findings(obj, copy, variant)
        finally:
            bpy.data.meshes.remove(copy)
        for material in _materials_of(obj):
            materials[material.name] = material
    for material in materials.values():
        findings += _material_findings(collection, material)
        for image in _images_of(material):
            images[image.name] = image
    for image in images.values():
        findings += _image_findings(collection, image)
    findings += _budget_findings(
        variant,
        asset_class,
        budget,
        meshes,
        tris_out,
        list(materials.values()),
        list(images.values()),
        root_name,
    )
    return findings


def _material_findings(collection: str, material: bpy.types.Material) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not re.fullmatch(rf"M_{re.escape(collection)}_[A-Za-z0-9]+", export_name(material.name)):
        findings.append(
            finding(
                "naming.material",
                material.name,
                f"Material {material.name} is not named M_{collection}_<Part>.",
            )
        )
    tree = material.node_tree
    if tree is None:
        findings.append(
            finding(
                "material.node_types",
                material.name,
                f"Material {material.name} has no node tree, so it cannot export a surface.",
            )
        )
        return findings
    for node in tree.nodes:
        if node.type not in ALLOWED_NODE_TYPES:
            findings.append(
                finding(
                    "material.node_types",
                    material.name,
                    f"{material.name} uses the {node.bl_idname} node '{node.name}'; export "
                    "materials allow only Image Texture, Normal Map, Separate Color, Principled "
                    "BSDF, Material Output, and the UV Map node that feeds image vectors.",
                )
            )
        if node.type == "TEX_IMAGE":
            problem = _coordinate_problem(node)
            if problem is not None:
                findings.append(
                    finding(
                        "material.uv_coordinates",
                        material.name,
                        f"{material.name}: Image Texture '{node.name}' {problem}.",
                    )
                )
    return findings


def _coordinate_problem(node: bpy.types.Node) -> str | None:
    socket = node.inputs.get("Vector")
    if socket is None or not socket.is_linked:
        return "has no UV input, so Blender samples Generated coordinates"
    link = socket.links[0]
    source = link.from_node
    while source.type == "REROUTE" and source.inputs[0].is_linked:
        source = source.inputs[0].links[0].from_node
    if source.type == "UVMAP":
        if source.uv_map == _UV_MAP:
            return None
        return f"samples UV map '{source.uv_map}', not UVMap"
    return f"takes coordinates from '{source.name}' ({link.from_socket.name}), not a UV Map node"


def _image_findings(collection: str, image: bpy.types.Image) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not re.fullmatch(
        rf"T_{re.escape(collection)}_[A-Za-z0-9]+_(BC|N|ORM)", export_name(image.name)
    ):
        findings.append(
            finding(
                "naming.texture",
                image.name,
                f"Image {image.name} is not named T_{collection}_<Part>_BC, _N, or _ORM.",
            )
        )
    width, height = image.size
    if width != height or width <= 0 or width & (width - 1):
        findings.append(
            finding(
                "texture.power_of_two",
                image.name,
                f"{image.name} is {width}x{height}; textures must be power-of-two squares.",
            )
        )
    return findings


def _texel_findings(
    obj: bpy.types.Object, copy: bpy.types.Mesh, variant: str
) -> list[dict[str, str]]:
    uv_area, world_area = _areas(copy)
    images = [image for material in _materials_of(obj) for image in _images_of(material)]
    if uv_area <= 0 or world_area <= 0 or not images:
        return []
    max_px = max(max(image.size) for image in images)
    density = max_px * math.sqrt(uv_area / world_area)
    minimum = TEXEL_DENSITY_MIN[variant]
    if density >= minimum:
        return []
    return [
        finding(
            "texel.density",
            obj.name,
            f"{obj.name} reaches {density:.0f} px/m; environment pieces need at least "
            f"{minimum:.0f} px/m on {variant}.",
        )
    ]


def _budget_findings(
    variant: str,
    asset_class: str,
    budget: dict[str, int],
    meshes: list[bpy.types.Object],
    tris: dict[str, int],
    materials: list[bpy.types.Material],
    images: list[bpy.types.Image],
    root_name: str,
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    counted = [obj for obj in meshes if not _LOD_EXTRA.search(obj.name)]
    total = sum(tris.get(obj.name, 0) for obj in counted)
    if counted and total > budget["tris"]:
        worst = max(counted, key=lambda obj: (tris.get(obj.name, 0), obj.name))
        findings.append(
            finding(
                "budget.tris",
                worst.name,
                f"{variant} triangles total {total}; the {asset_class} {variant} budget is "
                f"{budget['tris']} (largest: {worst.name} with {tris.get(worst.name, 0)}).",
            )
        )
    if len(materials) > budget["materials"]:
        findings.append(
            finding(
                "budget.materials",
                root_name,
                f"{variant} uses {len(materials)} materials; the {asset_class} {variant} limit "
                f"is {budget['materials']}.",
            )
        )
    if asset_class != "environment_piece" and images:
        largest = max(images, key=lambda image: max(image.size))
        if max(largest.size) > budget["max_texture_px"]:
            findings.append(
                finding(
                    "budget.texture_size",
                    largest.name,
                    f"{largest.name} is {max(largest.size)} px; the {asset_class} {variant} "
                    f"maximum is {budget['max_texture_px']} px.",
                )
            )
    return findings


def _variant_name_findings(
    desktop: list[bpy.types.Object], mobile: list[bpy.types.Object]
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    desktop_meshes = {obj.name for obj in desktop if obj.type == "MESH"}
    mobile_objects = [obj for obj in mobile if obj.type in {"MESH", "EMPTY"}]
    mobile_names = {_variant_key(obj.name) for obj in mobile_objects}
    for obj in mobile_objects:
        if _variant_key(obj.name) not in desktop_meshes:
            findings.append(
                finding(
                    "variants.names_match",
                    obj.name,
                    f"{obj.name} has no Desktop object named {_variant_key(obj.name)}.",
                )
            )
    for name in sorted(desktop_meshes - mobile_names):
        findings.append(
            finding(
                "variants.names_match",
                name,
                f"Desktop object {name} has no Mobile counterpart named {name}{MOBILE_SUFFIX}.",
            )
        )
    findings += _name_set_findings(
        "material",
        {material.name for obj in desktop for material in _materials_of(obj)},
        {material.name for obj in mobile for material in _materials_of(obj)},
    )
    findings += _name_set_findings(
        "image",
        {
            image.name
            for obj in desktop
            for material in _materials_of(obj)
            for image in _images_of(material)
        },
        {
            image.name
            for obj in mobile
            for material in _materials_of(obj)
            for image in _images_of(material)
        },
    )
    return findings


def _name_set_findings(kind: str, desktop: set[str], mobile: set[str]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    mobile_keys = {_variant_key(name) for name in mobile}
    for name in sorted(mobile):
        if _variant_key(name) not in desktop:
            findings.append(
                finding(
                    "variants.names_match",
                    name,
                    f"Mobile {kind} {name} has no Desktop {kind} named {_variant_key(name)}.",
                )
            )
    for name in sorted(desktop - mobile_keys):
        findings.append(
            finding(
                "variants.names_match",
                name,
                f"Desktop {kind} {name} has no Mobile counterpart named {name}{MOBILE_SUFFIX}.",
            )
        )
    return findings


def _evaluated_copy(obj: bpy.types.Object) -> bpy.types.Mesh:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), depsgraph=depsgraph)


def _materials_of(obj: bpy.types.Object) -> list[bpy.types.Material]:
    return [slot.material for slot in obj.material_slots if slot.material is not None]


def _images_of(material: bpy.types.Material) -> list[bpy.types.Image]:
    if material.node_tree is None:
        return []
    return [
        node.image
        for node in material.node_tree.nodes
        if node.type == "TEX_IMAGE" and node.image is not None
    ]


def _areas(mesh: bpy.types.Mesh) -> tuple[float, float]:
    """Return (UV area, world area) of the mesh, for the texel density estimate."""
    layer = mesh.uv_layers[0].data if mesh.uv_layers else None
    uv_total = 0.0
    if layer is not None:
        for poly in mesh.polygons:
            points = [
                layer[index].uv
                for index in range(poly.loop_start, poly.loop_start + poly.loop_total)
            ]
            for index in range(1, len(points) - 1):
                a, b, c = points[0], points[index], points[index + 1]
                uv_total += abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)) / 2
    world_total = sum(poly.area for poly in mesh.polygons)
    return uv_total, world_total


def _close(values: Any, expected: tuple[float, ...], tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(values, expected, strict=True))


def _local_bounds(obj: bpy.types.Object) -> dict[str, list[float]]:
    """The object-local bounding box in meters, which the UE static mesh's local bounds must match.

    The finalize pivot check (#69, AC5) compares the imported part's bounds with this box.
    """
    corners = [Vector(corner) for corner in obj.bound_box]
    return {
        "min": _rounded([min(corner[axis] for corner in corners) for axis in range(3)]),
        "max": _rounded([max(corner[axis] for corner in corners) for axis in range(3)]),
    }


def _rounded(values: Any) -> list[float]:
    return [round(float(value), 6) for value in values]


def _format(values: Any) -> str:
    return "(" + ", ".join(f"{float(value):.4f}" for value in values) + ")"
