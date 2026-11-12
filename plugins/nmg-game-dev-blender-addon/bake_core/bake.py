"""Cycles bake of each channel into float images, from temporary per-channel material copies.

Base color, roughness, and metallic are baked as EMIT of an Emission substitute for each
Principled BSDF, so Mix and Add Shader trees and any coordinates are handled. Normal uses
NORMAL in tangent space (OpenGL swizzle) and AO uses AO on the authored materials' copies.
The authored materials are never changed: every pass runs on a copy that is removed afterward.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import bpy

from .errors import BakeError

CHANNELS: tuple[str, ...] = ("BC", "ROUGH", "METAL", "N", "AO")
BAKE_TYPES: dict[str, str] = {
    "BC": "EMIT",
    "ROUGH": "EMIT",
    "METAL": "EMIT",
    "N": "NORMAL",
    "AO": "AO",
}
# Principled input whose value each EMIT channel reads.
_EMIT_SOCKET: dict[str, str] = {"BC": "Base Color", "ROUGH": "Roughness", "METAL": "Metallic"}
_NORMAL_KWARGS: dict[str, str] = {
    "normal_space": "TANGENT",
    "normal_r": "POS_X",
    "normal_g": "POS_Y",
    "normal_b": "POS_Z",
}
TARGET_NODE = "__nmg_bake_target"


def bake_margin(size: int) -> int:
    """Island margin in pixels: four pixels, or size/128 when larger (design § Baking)."""
    return max(4, size // 128)


def select_device(requested: str) -> str:
    """Set the context scene to Cycles and return the device used: GPU only when available."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    if requested == "GPU" and _gpu_available():
        scene.cycles.device = "GPU"
        return "GPU"
    scene.cycles.device = "CPU"
    return "CPU"


def configure(samples: int) -> None:
    bpy.context.scene.cycles.samples = samples


def new_channel_image(name: str, size: int) -> bpy.types.Image:
    """A float RGBA image that a bake writes raw values into; the pack step encodes it."""
    image = bpy.data.images.new(name, size, size, alpha=True, float_buffer=True)
    image.colorspace_settings.name = "Non-Color"
    return image


def bake_channel(
    meshes: Sequence[bpy.types.Object],
    sources: Sequence[bpy.types.Material],
    targets: Sequence[bpy.types.Image],
    channel: str,
    size: int,
) -> None:
    """Bake one channel of every source material into targets[i], one source per pass.

    Each pass leaves exactly one image-texture node in the object: the active source's target.
    The other copies carry no image node, so their faces cannot bake into another source's image.
    targets may repeat one image (a merged atlas): the image clears on its first pass only, and
    later passes add their faces to it.

    Probe finding (Blender 5.2.3, headless): one bake call whose two materials target a single
    shared image overwrites the whole image with the last material's value, which is why the
    atlas is baked in sequential passes instead.
    """
    copies = [_channel_copy(source, channel, index, size) for index, source in enumerate(sources)]
    originals = {mesh.name: list(mesh.data.materials) for mesh in meshes}
    active_slots = {mesh.name: mesh.active_material_index for mesh in meshes}
    index_of = {source.as_pointer(): index for index, source in enumerate(sources)}
    try:
        for mesh in meshes:
            slots = mesh.data.materials
            for slot_index, material in enumerate(list(slots)):
                if material is not None and material.as_pointer() in index_of:
                    slots[slot_index] = copies[index_of[material.as_pointer()]]
        _select(meshes)
        cleared: set[int] = set()
        for active, _ in enumerate(copies):
            for other, copy in enumerate(copies):
                tree = copy.node_tree
                for node in tree.nodes:
                    node.select = False
                target = _set_target(copy, targets[other] if other == active else None)
                if target is not None:
                    tree.nodes.active = target
                    target.select = True
                else:
                    tree.nodes.active = _output(copy)
            image_key = targets[active].as_pointer()
            clear = image_key not in cleared
            cleared.add(image_key)
            bpy.ops.object.bake(
                type=BAKE_TYPES[channel],
                margin=bake_margin(size),
                use_clear=clear,
                target="IMAGE_TEXTURES",
                save_mode="INTERNAL",
                **(_NORMAL_KWARGS if channel == "N" else {}),
            )
    except RuntimeError as error:
        raise BakeError(
            "internal_error",
            f"Blender refused the {channel} bake: {error}",
            target=sources[0].name if sources else "",
        ) from error
    finally:
        for mesh in meshes:
            _restore_slots(mesh, originals[mesh.name])
            mesh.active_material_index = active_slots[mesh.name]
        for copy in copies:
            bpy.data.materials.remove(copy)


def bake_transfer(
    source: bpy.types.Object,
    copy: bpy.types.Object,
    channel: str,
    target: bpy.types.Image,
    size: int,
    cage_extrusion: float,
    max_ray_distance: float,
    clear: bool,
) -> None:
    """Selected-to-active bake of one channel: source's surface onto copy's target image (#139).

    For the pass, the source's slots hold channel copies of its materials (EMIT for base color,
    roughness, and metallic; tangent-space NORMAL; AO), and the copy's only slot holds a temporary
    material whose image node is the active target. Both are restored afterward, so the source
    keeps its authored materials. clear is True only on the first pass into a shared target.
    """
    channel_copies: dict[int, bpy.types.Material] = {}
    replacements: dict[int, bpy.types.Material] = {}
    target_material = _target_material(target)
    try:
        for index, material in enumerate(source.data.materials):
            if material is None:
                continue
            key = material.as_pointer()
            if key not in channel_copies:
                channel_copies[key] = _channel_copy(material, channel, len(channel_copies), size)
            replacements[index] = channel_copies[key]
        with _slots_replaced(source, replacements):
            _set_slots(copy, target_material)
            select_only([source, copy], copy)
            _run_bake(
                BAKE_TYPES[channel],
                margin=bake_margin(size),
                clear=clear,
                selected=True,
                cage_extrusion=cage_extrusion,
                max_ray_distance=max_ray_distance,
                normal=channel == "N",
            )
    finally:
        copy.data.materials.clear()
        bpy.data.materials.remove(target_material)
        for material in channel_copies.values():
            bpy.data.materials.remove(material)


def bake_coverage(
    source: bpy.types.Object,
    copy: bpy.types.Object,
    target: bpy.types.Image,
    cage_extrusion: float,
    max_ray_distance: float,
    clear: bool,
) -> None:
    """Constant-white EMIT from source's hits onto copy's target, with no margin (#139 coverage).

    Texels the copy's rays reached on the source come out white; the rest stay black.
    """
    constant = _constant_material()
    target_material = _target_material(target)
    try:
        replacements = {index: constant for index in range(len(source.data.materials))}
        with _slots_replaced(source, replacements):
            _set_slots(copy, target_material)
            select_only([source, copy], copy)
            _run_bake(
                "EMIT",
                margin=0,
                clear=clear,
                selected=True,
                cage_extrusion=cage_extrusion,
                max_ray_distance=max_ray_distance,
                normal=False,
            )
    finally:
        copy.data.materials.clear()
        bpy.data.materials.remove(target_material)
        bpy.data.materials.remove(constant)


def bake_island(
    copy: bpy.types.Object,
    target: bpy.types.Image,
    clear: bool,
) -> None:
    """Constant-white EMIT of copy onto its own UV islands, with no margin (#139 coverage)."""
    island = _target_material(target, emit_white=True)
    try:
        _set_slots(copy, island)
        select_only([copy], copy)
        _run_bake(
            "EMIT",
            margin=0,
            clear=clear,
            selected=False,
            cage_extrusion=0.0,
            max_ray_distance=0.0,
            normal=False,
        )
    finally:
        copy.data.materials.clear()
        bpy.data.materials.remove(island)


def select_only(objects: Sequence[bpy.types.Object], active: bpy.types.Object) -> None:
    """Select exactly objects (in object mode) and make active the active one."""
    view_layer = bpy.context.view_layer
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    view_layer.objects.active = active


@contextmanager
def _slots_replaced(
    obj: bpy.types.Object, replacements: dict[int, bpy.types.Material]
) -> Iterator[None]:
    """Swap the given slot materials for the duration of the block, then restore every slot."""
    originals = list(obj.data.materials)
    try:
        for index, material in replacements.items():
            obj.data.materials[index] = material
        yield
    finally:
        _restore_slots(obj, originals)


def _set_slots(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    """Give obj one slot holding material, with every face on it."""
    obj.data.materials.clear()
    obj.data.materials.append(material)
    obj.data.polygons.foreach_set("material_index", [0] * len(obj.data.polygons))


def _target_material(image: bpy.types.Image, *, emit_white: bool = False) -> bpy.types.Material:
    """A temporary material whose image node is the active bake target (and white EMIT if asked)."""
    material = bpy.data.materials.new("__nmg_bake_target")
    material.use_nodes = True
    if emit_white:
        _make_emission(material)
    node = _set_target(material, image)
    material.node_tree.nodes.active = node
    return material


def _constant_material() -> bpy.types.Material:
    material = bpy.data.materials.new("__nmg_bake_constant")
    material.use_nodes = True
    _make_emission(material)
    return material


def _make_emission(material: bpy.types.Material) -> None:
    """Replace the Principled BSDF with a white Emission feeding the output."""
    tree = material.node_tree
    output = _output(material)
    for node in [node for node in tree.nodes if node.type == "BSDF_PRINCIPLED"]:
        tree.nodes.remove(node)
    emission = tree.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])


def _run_bake(
    bake_type: str,
    *,
    margin: int,
    clear: bool,
    selected: bool,
    cage_extrusion: float,
    max_ray_distance: float,
    normal: bool,
) -> None:
    try:
        bpy.ops.object.bake(
            type=bake_type,
            margin=margin,
            use_clear=clear,
            target="IMAGE_TEXTURES",
            save_mode="INTERNAL",
            use_selected_to_active=selected,
            use_cage=False,
            cage_extrusion=cage_extrusion,
            max_ray_distance=max_ray_distance,
            **(_NORMAL_KWARGS if normal else {}),
        )
    except RuntimeError as error:
        raise BakeError(
            "internal_error",
            f"Blender refused the {bake_type} bake: {error}",
        ) from error


def _channel_copy(
    source: bpy.types.Material, channel: str, index: int, size: int
) -> bpy.types.Material:
    copy = source.copy()
    copy.name = f"__nmg_bake_{channel}_{index}"
    if channel in _EMIT_SOCKET:
        tree = copy.node_tree
        for node in [node for node in tree.nodes if node.type == "BSDF_PRINCIPLED"]:
            _emit_in_place(tree, node, _EMIT_SOCKET[channel])
    return copy


def _emit_in_place(tree: bpy.types.NodeTree, node: bpy.types.Node, socket: str) -> None:
    """Replace a Principled BSDF with an Emission that carries one of its input values."""
    source = node.inputs[socket]
    emission = tree.nodes.new("ShaderNodeEmission")
    if source.is_linked:
        tree.links.new(source.links[0].from_socket, emission.inputs["Color"])
    else:
        value = source.default_value
        if isinstance(value, float):
            emission.inputs["Color"].default_value = (value, value, value, 1.0)
        else:
            emission.inputs["Color"].default_value = (value[0], value[1], value[2], 1.0)
    for link in list(node.outputs["BSDF"].links):
        tree.links.new(emission.outputs["Emission"], link.to_socket)
    tree.nodes.remove(node)


def _set_target(copy: bpy.types.Material, image: bpy.types.Image | None) -> bpy.types.Node | None:
    """Bind the copy's one image-texture target to image, or remove it when image is None."""
    tree = copy.node_tree
    node = tree.nodes.get(TARGET_NODE)
    if image is None:
        if node is not None:
            tree.nodes.remove(node)
        return None
    if node is None:
        node = tree.nodes.new("ShaderNodeTexImage")
        node.name = TARGET_NODE
        node.label = TARGET_NODE
    node.image = image
    return node


def _output(copy: bpy.types.Material) -> bpy.types.Node:
    tree = copy.node_tree
    return next(
        (node for node in tree.nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output),
        next(node for node in tree.nodes if node.type == "OUTPUT_MATERIAL"),
    )


def _select(meshes: Sequence[bpy.types.Object]) -> None:
    view_layer = bpy.context.view_layer
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in view_layer.objects:
        obj.select_set(False)
    for obj in meshes:
        obj.select_set(True)
    view_layer.objects.active = meshes[0]


def _restore_slots(mesh: bpy.types.Object, materials: list[bpy.types.Material | None]) -> None:
    """Put the original materials back in place, slot by slot.

    Popping slots would clamp the face material indices of the removed slots to 0, which silently
    moves every face onto the first material. Assigning in place keeps the slot count, so the
    indices stay as they were.
    """
    slots = mesh.data.materials
    for index, material in enumerate(materials):
        slots[index] = material


def _gpu_available() -> bool:
    """True when Cycles lists a compute device other than the CPU. Headless hosts have none."""
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except KeyError:
        return False
    items = prefs.bl_rna.properties["compute_device_type"].enum_items
    for item in items:
        if item.identifier in ("NONE", "CPU"):
            continue
        try:
            prefs.compute_device_type = item.identifier
            prefs.get_devices(item.identifier)
        except (TypeError, RuntimeError, AttributeError):
            continue
        accelerators = [device for device in prefs.devices if device.type != "CPU"]
        if accelerators:
            for device in prefs.devices:
                device.use = device.type != "CPU"
            return True
    return False
