"""Review renders and the texture proof sheet.

Every render runs in a temporary scene that links the asset collections and adds one camera and
one lighting rig. The rig and the camera distance are identical for every view and variant, and
the scene is removed afterward, so the user's scenes are unchanged.
"""

from __future__ import annotations

import math
import re
import shutil
import tempfile
from array import array
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector

from .report import ContractError

REVIEW_SCENE = "__nmg_review"
DEFAULT_RESOLUTION = 1024
SAMPLES = 16
FOCAL_MM = 50.0
SENSOR_MM = 36.0
ELEVATION = math.radians(20.0)
MARGIN = 1.10
VIEWS: dict[str, Vector] = {
    "front": Vector((0.0, -1.0, 0.0)),
    "back": Vector((0.0, 1.0, 0.0)),
    "side": Vector((1.0, 0.0, 0.0)),
    "three_quarter": Vector((1.0, -1.0, 0.0)).normalized(),
}
_SUN_ROTATIONS = (
    (math.radians(50.0), 0.0, math.radians(35.0)),
    (math.radians(60.0), 0.0, math.radians(-120.0)),
    (math.radians(30.0), 0.0, math.radians(160.0)),
)
_DATA_KINDS = (
    "objects",
    "collections",
    "meshes",
    "materials",
    "images",
    "lights",
    "cameras",
    "worlds",
)
_LABEL_SCALE = 3
_LABEL_BAND = 40
_GAP = 16
_LABEL_COLOR = (0.1, 0.1, 0.1, 1.0)
_GLYPHS: dict[str, tuple[str, ...]] = {
    "a": (".....", ".....", ".###.", "....#", ".####", "#...#", ".####"),
    "b": ("#....", "#....", "####.", "#...#", "#...#", "#...#", "####."),
    "d": ("....#", "....#", ".####", "#...#", "#...#", "#...#", ".####"),
    "e": (".....", ".....", ".###.", "#...#", "#####", "#....", ".####"),
    "i": ("..#..", ".....", ".##..", "..#..", "..#..", "..#..", ".###."),
    "k": ("#....", "#....", "#..#.", "#.#..", "##...", "#.#..", "#..#."),
    "m": (".....", ".....", "##.#.", "#.#.#", "#.#.#", "#.#.#", "#.#.#"),
    "o": (".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###."),
    "p": (".....", ".....", "####.", "#...#", "####.", "#....", "#...."),
    "r": (".....", ".....", "#.##.", "##..#", "#....", "#....", "#...."),
    "t": (".#...", ".#...", "####.", ".#...", ".#...", ".#..#", "..##."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
}


def render_review(
    collection_name: str, out_dir: str | Path, resolution: int = DEFAULT_RESOLUTION
) -> dict[str, Any]:
    """Write <out>/<variant>/<Name>_{front,back,side,three_quarter}.png for each variant."""
    asset = bpy.data.collections.get(collection_name)
    if asset is None:
        raise ContractError(
            "render.asset_missing",
            f"No collection named {collection_name} is in the open file.",
            "Open the file that holds the asset, or create its collection, then rerun.",
        )
    variants: list[tuple[str, bpy.types.Collection]] = [("desktop", asset)]
    mobile = bpy.data.collections.get(f"{collection_name}_Mobile")
    if mobile is not None:
        variants.append(("mobile", mobile))

    files: list[str] = []
    for variant, collection in variants:
        folder = Path(out_dir) / variant
        folder.mkdir(parents=True, exist_ok=True)
        outputs = {view: folder / f"{collection_name}_{view}.png" for view in VIEWS}
        _render_views([collection], outputs, resolution)
        files += [str(path) for path in outputs.values()]
    return {"files": files}


def render_texture_proof(
    variant_dir: str | Path,
    out_dir: str | Path,
    pre_bake: str | Path | None = None,
    collection: str | None = None,
    resolution: int = DEFAULT_RESOLUTION,
) -> dict[str, Any]:
    """Write <out>/<variant>/<Name>_proof.png: pre-bake, baked, and re-imported side by side."""
    variant = Path(variant_dir)
    fbx_files = sorted(variant.glob("SM_*.fbx"))
    if not fbx_files:
        raise ContractError(
            "render.proof_fbx_missing",
            f"No SM_<Name>.fbx is in {variant}.",
            "Export the variant before rendering the texture proof.",
        )
    fbx = fbx_files[0]
    asset = fbx.stem.removeprefix("SM_")
    baked = bpy.data.collections.get(collection or asset)
    if baked is None:
        raise ContractError(
            "render.proof_collection_missing",
            f"No collection named {collection or asset} is in the open file.",
            "Open the file that holds the baked asset, or pass its collection name.",
        )
    if pre_bake is not None and not Path(pre_bake).is_file():
        raise ContractError(
            "render.pre_bake_missing",
            f"The pre-bake render {pre_bake} does not exist.",
            "Render the asset before baking, or omit pre_bake for a two-panel proof.",
        )

    folder = Path(out_dir) / variant.name.lower()
    folder.mkdir(parents=True, exist_ok=True)
    proof = folder / f"{asset}_proof.png"
    workdir = Path(tempfile.mkdtemp(prefix="nmg_proof_"))
    before = _datablock_pointers()
    try:
        baked_png = workdir / "baked.png"
        reimported_png = workdir / "re-imported.png"
        frame = _render_views([baked], {"three_quarter": baked_png}, resolution)
        reimported = _import_reimported(fbx, variant)
        _render_views([reimported], {"three_quarter": reimported_png}, resolution, frame)
        panels: list[tuple[str, Path]] = []
        if pre_bake is not None:
            panels.append(("pre-bake", Path(pre_bake)))
        panels += [("baked", baked_png), ("re-imported", reimported_png)]
        _compose(panels, proof)
    finally:
        _remove_new_datablocks(before)
        shutil.rmtree(workdir, ignore_errors=True)
    return {"proof": str(proof)}


def _render_views(
    collections: Iterable[bpy.types.Collection],
    outputs: Mapping[str, Path],
    resolution: int,
    frame: tuple[Vector, float] | None = None,
) -> tuple[Vector, float]:
    """Render each view into its output path and return the (center, distance) framing used."""
    collection_list = list(collections)
    scene = bpy.data.scenes.new(REVIEW_SCENE)
    helpers: list[bpy.types.Object] = []
    world: bpy.types.World | None = None
    try:
        for collection in collection_list:
            scene.collection.children.link(collection)
        scene.view_layers[0].update()
        center, distance = frame if frame is not None else _frame(collection_list)
        camera, helpers, world = _build_rig(scene)
        _set_render(scene, resolution)
        for view, path in outputs.items():
            _place_camera(camera, center, distance, VIEWS[view])
            scene.render.filepath = str(path)
            with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
                bpy.ops.render.render(write_still=True)
            if not path.is_file():
                raise ContractError(
                    "render.failed",
                    f"Blender did not write {path}.",
                    "Check the Blender log, then rerun the render.",
                )
        return center, distance
    finally:
        _teardown(scene, helpers, world)


def _frame(collections: list[bpy.types.Collection]) -> tuple[Vector, float]:
    """Center and camera distance that fit the bounding sphere of the meshes with a margin."""
    corners: list[Vector] = []
    for collection in collections:
        for obj in collection.all_objects:
            if obj.type == "MESH":
                corners += [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    if not corners:
        raise ContractError(
            "render.empty_asset",
            "The asset has no mesh to frame.",
            "Add geometry to the asset collection, then rerun the render.",
        )
    low = Vector(tuple(min(corner[axis] for corner in corners) for axis in range(3)))
    high = Vector(tuple(max(corner[axis] for corner in corners) for axis in range(3)))
    radius = (high - low).length / 2
    half_fov = math.atan((SENSOR_MM / 2) / FOCAL_MM)
    return (low + high) / 2, radius * MARGIN / math.sin(half_fov)


def _build_rig(
    scene: bpy.types.Scene,
) -> tuple[bpy.types.Object, list[bpy.types.Object], bpy.types.World]:
    world = bpy.data.worlds.new("__nmg_review_world")
    world.use_nodes = True
    background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
    background.inputs["Color"].default_value = (0.5, 0.5, 0.5, 1.0)
    background.inputs["Strength"].default_value = 1.0
    scene.world = world

    helpers: list[bpy.types.Object] = []
    for index, rotation in enumerate(_SUN_ROTATIONS):
        light_data = bpy.data.lights.new(f"__nmg_review_sun_{index}", type="SUN")
        light_data.energy = 3.0
        light = bpy.data.objects.new(light_data.name, light_data)
        light.rotation_euler = rotation
        scene.collection.objects.link(light)
        helpers.append(light)

    camera_data = bpy.data.cameras.new("__nmg_review_camera")
    camera_data.lens = FOCAL_MM
    camera_data.sensor_width = SENSOR_MM
    camera = bpy.data.objects.new("__nmg_review_camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    helpers.append(camera)
    return camera, helpers, world


def _place_camera(
    camera: bpy.types.Object, center: Vector, distance: float, direction: Vector
) -> None:
    offset = direction * math.cos(ELEVATION) + Vector((0.0, 0.0, math.sin(ELEVATION)))
    camera.location = center + offset * distance
    camera.rotation_mode = "QUATERNION"
    camera.rotation_quaternion = (center - camera.location).to_track_quat("-Z", "Y")
    camera.data.clip_end = max(100.0, distance * 4.0)


def _set_render(scene: bpy.types.Scene, resolution: int) -> None:
    scene.render.engine = _eevee_identifier()
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.eevee.taa_render_samples = SAMPLES


def _eevee_identifier() -> str:
    items = bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    matches = [item.identifier for item in items if item.identifier.startswith("BLENDER_EEVEE")]
    if not matches:
        raise ContractError(
            "render.engine_missing",
            "This Blender build has no EEVEE render engine.",
            "Run the review renders in Blender 5.2 or newer.",
        )
    return matches[-1]


def _teardown(
    scene: bpy.types.Scene,
    helpers: list[bpy.types.Object],
    world: bpy.types.World | None,
) -> None:
    scene.camera = None
    for obj in helpers:
        data = obj.data
        bpy.data.objects.remove(obj)
        if isinstance(data, bpy.types.Light):
            bpy.data.lights.remove(data)
        elif isinstance(data, bpy.types.Camera):
            bpy.data.cameras.remove(data)
    scene.world = None
    bpy.data.scenes.remove(scene)
    if world is not None:
        bpy.data.worlds.remove(world)


def _import_reimported(fbx: Path, variant: Path) -> bpy.types.Collection:
    """Import the FBX into a scratch scene, wire ORM as the Unreal import does, and return it."""
    scratch = bpy.data.scenes.new("__nmg_proof_import")
    try:
        with bpy.context.temp_override(scene=scratch, view_layer=scratch.view_layers[0]):
            bpy.ops.import_scene.fbx(filepath=str(fbx))
        target = bpy.data.collections.new("__nmg_reimported")
        for obj in list(scratch.objects):
            for owner in list(obj.users_collection):
                owner.objects.unlink(obj)
            target.objects.link(obj)
    finally:
        bpy.data.scenes.remove(scratch)
    materials = {
        slot.material
        for obj in target.objects
        for slot in obj.material_slots
        if slot.material is not None
    }
    for material in materials:
        _wire_orm(material, variant)
    return target


def _wire_orm(material: bpy.types.Material, variant: Path) -> None:
    """Route T_<Name>_<Part>_ORM through Separate Color: G to Roughness, B to Metallic."""
    tree = material.node_tree
    if tree is None:
        return
    bsdf = next((node for node in tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return
    stem = re.sub(r"\.\d+$", "", material.name).removeprefix("M_")
    orm = variant / f"T_{stem}_ORM.png"
    if not orm.is_file():
        raise ContractError(
            "render.proof_orm_missing",
            f"{orm.name} is missing from {variant}.",
            "Export the variant so its ORM texture sits beside the FBX, then rerun the proof.",
        )
    for link in list(tree.links):
        if link.to_node == bsdf and link.to_socket.name in {"Roughness", "Metallic"}:
            tree.links.remove(link)
    image = bpy.data.images.load(str(orm), check_existing=False)
    image.colorspace_settings.name = "Non-Color"
    uv = tree.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    split = tree.nodes.new("ShaderNodeSeparateColor")
    tree.links.new(uv.outputs["UV"], texture.inputs["Vector"])
    tree.links.new(texture.outputs["Color"], split.inputs["Color"])
    tree.links.new(split.outputs["Green"], bsdf.inputs["Roughness"])
    tree.links.new(split.outputs["Blue"], bsdf.inputs["Metallic"])


def _compose(panels: list[tuple[str, Path]], path: Path) -> None:
    """Place the panels side by side under labeled bands and save the sheet as a PNG."""
    images = [bpy.data.images.load(str(panel), check_existing=False) for _, panel in panels]
    try:
        width = sum(image.size[0] for image in images) + _GAP * (len(images) - 1)
        height = _LABEL_BAND + max(image.size[1] for image in images)
        canvas = array("f", [1.0]) * (width * height * 4)
        scale = _label_scale(panels, images)
        x = 0
        for (label, _), image in zip(panels, images, strict=True):
            pixel_width, pixel_height = image.size
            pixels = array("f", [0.0]) * (pixel_width * pixel_height * 4)
            image.pixels.foreach_get(pixels)
            _blit(canvas, width, pixels, pixel_width, pixel_height, x)
            _draw_label(canvas, width, height, label, x + 4, scale)
            x += pixel_width + _GAP
        sheet = bpy.data.images.new("__nmg_proof_sheet", width, height, alpha=True)
        try:
            sheet.pixels.foreach_set(canvas)
            sheet.filepath_raw = str(path)
            sheet.file_format = "PNG"
            sheet.save()
        finally:
            bpy.data.images.remove(sheet)
    finally:
        for image in images:
            bpy.data.images.remove(image)


def _blit(
    canvas: array,
    canvas_width: int,
    pixels: array,
    width: int,
    height: int,
    x: int,
) -> None:
    row_length = width * 4
    for row in range(height):
        start = (row * canvas_width + x) * 4
        canvas[start : start + row_length] = pixels[row * row_length : (row + 1) * row_length]


def _label_scale(panels: list[tuple[str, Path]], images: list[bpy.types.Image]) -> int:
    """The largest glyph scale, up to _LABEL_SCALE, at which the longest label fits its panel."""
    longest = max(len(label) for label, _ in panels)
    narrowest = min(image.size[0] for image in images)
    return max(1, min(_LABEL_SCALE, narrowest // (6 * longest)))


def _draw_label(
    canvas: array, canvas_width: int, canvas_height: int, text: str, x: int, scale: int
) -> None:
    glyph_height = 7 * scale
    top = canvas_height - 1 - (_LABEL_BAND - glyph_height) // 2
    cursor = x
    for char in text:
        glyph = _GLYPHS.get(char, _GLYPHS[" "])
        for row, pattern in enumerate(glyph):
            for offset in range(scale):
                y = top - row * scale - offset
                for column, mark in enumerate(pattern):
                    if mark != "#":
                        continue
                    for step in range(scale):
                        _set_pixel(canvas, canvas_width, cursor + column * scale + step, y)
        cursor += 6 * scale


def _set_pixel(canvas: array, canvas_width: int, x: int, y: int) -> None:
    if x < 0 or x >= canvas_width or y < 0:
        return
    index = (y * canvas_width + x) * 4
    if index + 4 > len(canvas):
        return
    canvas[index : index + 4] = array("f", _LABEL_COLOR)


def _datablock_pointers() -> dict[str, set[int]]:
    return {kind: {item.as_pointer() for item in getattr(bpy.data, kind)} for kind in _DATA_KINDS}


def _remove_new_datablocks(before: dict[str, set[int]]) -> None:
    """Remove datablocks created since before, so the proof leaves no orphans behind."""
    for kind in _DATA_KINDS:
        collection = getattr(bpy.data, kind)
        created = [
            item for item in collection if item.as_pointer() not in before[kind] and _is_plain(item)
        ]
        for item in created:
            collection.remove(item)


def _is_plain(item: Any) -> bool:
    return not (isinstance(item, bpy.types.Image) and item.type != "IMAGE")
