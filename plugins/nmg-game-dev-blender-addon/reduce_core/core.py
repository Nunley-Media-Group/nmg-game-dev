"""reduce_asset and run_for_mcp: reduce a generated high-poly asset to its Desktop budget (#139).

Order: guard the request, read the sources, plan the budget split and bake settings, then work
only on reduced copies. Copies are decimated, unwrapped into one atlas, baked from each source
part, checked for ray misses, and packed into the contract texture set. Only after all of that
passes does commit touch the scene. A failure before commit removes every datablock the run
created, so the scene is unchanged.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import bpy

from ..bake_core import bake, pack, rewire, uv
from ..bake_core.errors import BakeError
from ..bake_core.state import datablock_pointers, remove_created
from ..utils.budgets import ASSET_CLASSES, TERRAIN_CLASS, BudgetOverrideError, resolve_budget
from ..variants_core.meshes import triangle_count
from . import commit, decimate, plan, transfer
from .plan import DEFAULTS, PartStats, ReduceError

ProgressSink = Callable[[float, str], None]
HIGH_SUFFIX = "_High"
_OVERRIDE_KEYS: tuple[str, ...] = ("share", "tris")
_SETTING_KEYS: tuple[str, ...] = ("cage_extrusion", "max_ray_distance")
_TEXTURE_KINDS: tuple[str, ...] = ("BC", "N", "ORM")
# Terrain (#154) is a heightfield with no triangle budget, so reduce refuses it.
_REDUCE_CLASSES: tuple[str, ...] = tuple(c for c in ASSET_CLASSES if c != TERRAIN_CLASS)


def reduce_asset(
    collection: str,
    asset_class: str,
    budgets_path: str | Path | None = None,
    *,
    device: str = "GPU",
    cage_extrusion: float | None = None,
    max_ray_distance: float | None = None,
    parts: Mapping[str, Mapping[str, Any]] | None = None,
    miss_threshold: float | None = None,
    out_dir: str | Path | None = None,
    progress: ProgressSink | None = None,
) -> dict[str, Any]:
    """Reduce <collection> to its Desktop budget and bake its look onto the reduced mesh.

    Returns the result dict (state "reduced" or "within_budget"). Raises ReduceError with a
    stable code, reason, and remediation. On a raised error the scene is as it was before the call.
    """
    emit = progress or _quiet
    try:
        return _reduce(
            collection,
            asset_class,
            budgets_path,
            device=device,
            cage_extrusion=cage_extrusion,
            max_ray_distance=max_ray_distance,
            parts=parts or {},
            miss_threshold=miss_threshold,
            out_dir=out_dir,
            emit=emit,
        )
    except ReduceError:
        raise
    except BakeError as error:
        raise ReduceError(
            "reduce.bake_failed", error.message, error.remediation, target=error.target
        ) from error
    except Exception as error:
        raise ReduceError(
            "reduce.internal_error",
            f"Unexpected error while reducing {collection}: {error}",
            "Check the Blender log for the traceback, fix the cause, and rerun.",
            target=collection,
        ) from error


def run_for_mcp(**kwargs: Any) -> dict[str, Any]:
    """The MCP entry point: the result dict, or {"error": {...}} instead of raising."""
    try:
        return reduce_asset(**kwargs)
    except ReduceError as error:
        return {"error": error.as_dict()}


def _reduce(
    collection_name: str,
    asset_class: str,
    budgets_path: str | Path | None,
    *,
    device: str,
    cage_extrusion: float | None,
    max_ray_distance: float | None,
    parts: Mapping[str, Mapping[str, Any]],
    miss_threshold: float | None,
    out_dir: str | Path | None,
    emit: ProgressSink,
) -> dict[str, Any]:
    collection = bpy.data.collections.get(collection_name)
    if collection is None:
        raise ReduceError(
            "reduce.collection_missing",
            f"No collection named {collection_name} is in the open file.",
            "Open the file that holds the asset, or pass its collection name.",
            target=collection_name,
        )
    if asset_class not in _REDUCE_CLASSES:
        raise ReduceError(
            "reduce.class_unsupported",
            f"Reduce does not support the {asset_class} asset class.",
            f"Use one of: {', '.join(_REDUCE_CLASSES)}.",
            target=collection_name,
        )
    high = bpy.data.collections.get(f"{collection_name}{HIGH_SUFFIX}")
    if _has_armature(collection) or (high is not None and _has_armature(high)):
        raise ReduceError(
            "reduce.rigged",
            f"{collection_name} contains an armature, so it cannot be reduced.",
            "Reduce before rigging: run reduce on the unrigged asset, then rig the result.",
            target=collection_name,
        )
    sources = _sources(collection, high)
    if not sources:
        raise ReduceError(
            "reduce.no_mesh",
            f"Collection {collection_name} has no mesh objects to reduce.",
            "Add mesh objects to the asset collection, then rerun the reduce.",
            target=collection_name,
        )
    for name, obj in sources:
        if not obj.data.materials or any(material is None for material in obj.data.materials):
            raise ReduceError(
                "reduce.no_material",
                f"Part {name} has a material slot with no material, so its look cannot be baked.",
                "Give every slot of every part a material, then rerun the reduce.",
                target=name,
            )

    budget = _budget(asset_class, budgets_path)
    texture_px = budget["max_texture_px"]
    names = [name for name, _ in sources]
    stats = {
        name: PartStats(area_m2=uv.world_area(obj), tris=triangle_count(obj.data))
        for name, obj in sources
    }
    total = sum(item.tris for item in stats.values())
    overrides = {
        name: {key: spec[key] for key in _OVERRIDE_KEYS if spec.get(key) is not None}
        for name, spec in parts.items()
    }
    per_part = {
        name: {key: spec[key] for key in _SETTING_KEYS if spec.get(key) is not None}
        for name, spec in parts.items()
    }
    targets = plan.split_budget(stats, budget["tris"], overrides)
    settings = plan.bake_settings(
        names,
        {"cage_extrusion": cage_extrusion, "max_ray_distance": max_ray_distance},
        per_part,
    )
    threshold = _threshold(miss_threshold)

    if high is None and total <= budget["tris"]:
        emit(1.0, "within budget")
        return _within_budget(collection_name, asset_class, budget, stats, texture_px)

    out = Path(out_dir) if out_dir is not None else _default_out(collection_name)
    scope = _Scope(
        [obj for _, obj in sources],
        [collection, high] if high is not None else [collection],
    )
    copies: dict[str, bpy.types.Object] = {}
    finals: dict[str, int] = {}
    try:
        temp = bpy.data.collections.new(commit.COPY_COLLECTION)
        bpy.context.scene.collection.children.link(temp)
        bpy.context.view_layer.update()
        emit(0.05, "building reduced copies")
        for name, obj in sources:
            copies[name] = decimate.make_copy(obj, temp, f"__nmg_reduce_{name}")
        copy_of = {obj.as_pointer(): copies[name] for name, obj in sources}
        for name, obj in sources:
            decimate.link_parent(obj, copies[name], copy_of)
        bpy.context.view_layer.update()
        for name in names:
            finals[name] = decimate.fit_copy(copies[name], targets[name], name)
        if sum(finals.values()) > budget["tris"]:
            raise ReduceError(
                "reduce.unreachable_target",
                f"The reduced parts total {sum(finals.values())} triangles, above the "
                f"{budget['tris']}-triangle budget.",
                "Raise the Desktop tris budget or the overrides, then rerun the reduce.",
                target=collection_name,
            )

        meshes = [copies[name] for name in names]
        emit(0.25, "unwrapping one atlas")
        uv.joint_unwrap(meshes)
        uv.finalize_unwrap(meshes)
        pairs = [(name, obj, copies[name]) for name, obj in sources]

        emit(0.35, "baking channels")
        device_used = bake.select_device(device)
        images = transfer.bake_channels(pairs, texture_px, settings)
        emit(0.8, "checking unbaked texels")
        shares = transfer.measure_coverage(pairs, texture_px, settings)
        plan.check_misses(shares, threshold, settings)
        scope.release()

        emit(0.9, "packing textures")
        paths = _pack_textures(collection_name, images, out)
        for image in images.values():
            bpy.data.images.remove(image)
        material = rewire.build_material(
            f"M_{collection_name}_Body", collection_name, "Body", paths
        )
        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None:
                node.image.pack()
        rewire.collapse(meshes, material)
    except BaseException:
        scope.rollback()
        raise

    commit.commit(collection, high, sources, copies, material)
    return _reduced(
        collection_name,
        asset_class,
        budget,
        names,
        stats,
        targets,
        finals,
        settings,
        shares,
        paths,
        device_used,
        texture_px,
    )


class _Scope:
    """Shows the sources for the bake, hides every other object from render, and undoes both.

    release restores visibility and the render settings. rollback also removes every datablock
    created since the scope opened, and the temporary copy collection, so a failed run leaves the
    file as it was.
    """

    def __init__(
        self,
        members: Sequence[bpy.types.Object],
        collections: Sequence[bpy.types.Collection],
    ) -> None:
        scene = bpy.context.scene
        self._scene = scene
        self._created = datablock_pointers()
        member_pointers = {obj.as_pointer() for obj in members}
        self._objects = [(obj, obj.hide_render, obj.hide_viewport) for obj in scene.objects]
        self._collections = [(item, item.hide_viewport, item.hide_render) for item in collections]
        self._layers = []
        for item in collections:
            layer = _layer_of(item)
            if layer is not None:
                self._layers.append((layer, layer.exclude, layer.hide_viewport))
        self._render = (scene.render.engine, scene.cycles.samples, scene.cycles.device)
        self._released = False

        for obj, _, _ in self._objects:
            member = obj.as_pointer() in member_pointers
            obj.hide_render = not member
            if member:
                obj.hide_viewport = False
        for item in collections:
            item.hide_viewport = False
            item.hide_render = False
        for layer, _, _ in self._layers:
            layer.exclude = False
            layer.hide_viewport = False
        bpy.context.view_layer.update()

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        for obj, render, viewport in self._objects:
            obj.hide_render = render
            obj.hide_viewport = viewport
        for item, viewport, render in self._collections:
            item.hide_viewport = viewport
            item.hide_render = render
        for layer, exclude, viewport in self._layers:
            layer.exclude = exclude
            layer.hide_viewport = viewport
        engine, samples, device = self._render
        self._scene.render.engine = engine
        self._scene.cycles.samples = samples
        self._scene.cycles.device = device

    def rollback(self) -> None:
        self.release()
        remove_created(self._created)
        temp = bpy.data.collections.get(commit.COPY_COLLECTION)
        if temp is not None:
            bpy.data.collections.remove(temp)


def _layer_of(collection: bpy.types.Collection) -> bpy.types.LayerCollection | None:
    stack = [bpy.context.view_layer.layer_collection]
    while stack:
        layer = stack.pop()
        if layer.collection.as_pointer() == collection.as_pointer():
            return layer
        stack.extend(layer.children)
    return None


def _has_armature(collection: bpy.types.Collection) -> bool:
    return any(obj.type == "ARMATURE" for obj in collection.all_objects)


def _sources(
    collection: bpy.types.Collection, high: bpy.types.Collection | None
) -> list[tuple[str, bpy.types.Object]]:
    """The part meshes and their reduced names: <Name>'s meshes, or <Name>_High's when it exists."""
    if high is not None:
        found = [
            (str(obj.get(commit.SOURCE_PROPERTY) or _without_high(obj.name)), obj)
            for obj in high.all_objects
            if obj.type == "MESH"
        ]
    else:
        found = [(obj.name, obj) for obj in collection.all_objects if obj.type == "MESH"]
    return sorted(found, key=lambda item: item[0])


def _without_high(name: str) -> str:
    return name[: -len(HIGH_SUFFIX)] if name.endswith(HIGH_SUFFIX) else name


def _budget(asset_class: str, budgets_path: str | Path | None) -> dict[str, int]:
    try:
        return resolve_budget(asset_class, str(budgets_path) if budgets_path else None, "desktop")
    except BudgetOverrideError as error:
        raise ReduceError(
            "reduce.budget_invalid", error.message, error.remediation, target=asset_class
        ) from error


def _threshold(value: float | None) -> float:
    threshold = DEFAULTS["miss_threshold"] if value is None else value
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, int | float)
        or not 0 <= threshold <= 1
    ):
        raise ReduceError(
            "reduce.invalid_override",
            f"miss_threshold must be a number from 0 to 1, got {threshold!r}.",
            "Set miss_threshold to a fraction such as 0.01.",
        )
    return float(threshold)


def _default_out(collection_name: str) -> Path:
    blend = bpy.data.filepath
    base = Path(blend).parent if blend else Path(tempfile.gettempdir()) / "nmg_reduce"
    return base / "Reduced" / collection_name


def _pack_textures(asset: str, images: Mapping[str, bpy.types.Image], out: Path) -> dict[str, Path]:
    """Write T_<Name>_Body_{BC,N,ORM} into out, from the baked float channels."""
    out.mkdir(parents=True, exist_ok=True)
    rgba = {channel: pack.read_rgba(image) for channel, image in images.items()}
    channels = {
        "BC": pack.base_color_rgb(rgba["BC"]),
        "N": pack.normal_rgb(rgba["N"]),
        "ORM": pack.orm_rgb(rgba["AO"], rgba["ROUGH"], rgba["METAL"]),
    }
    paths: dict[str, Path] = {}
    for kind in _TEXTURE_KINDS:
        image_name = f"T_{asset}_Body_{kind}"
        path = out / f"{image_name}.png"
        written = pack.write_png(image_name, channels[kind], kind, path)
        bpy.data.images.remove(written)
        paths[kind] = path
    return paths


def _within_budget(
    collection_name: str,
    asset_class: str,
    budget: Mapping[str, int],
    stats: Mapping[str, PartStats],
    texture_px: int,
) -> dict[str, Any]:
    total = sum(item.tris for item in stats.values())
    return {
        "kind": "reduce",
        "state": "within_budget",
        "collection": collection_name,
        "asset_class": asset_class,
        "budget": budget["tris"],
        "parts": {
            name: {
                "source_tris": item.tris,
                "target": item.tris,
                "final_tris": item.tris,
                "cage_extrusion": None,
                "max_ray_distance": None,
                "unbaked_share": None,
            }
            for name, item in stats.items()
        },
        "total_tris": total,
        "textures": {},
        "texture_px": texture_px,
        "device": None,
        "summary": f"{collection_name} is within its {budget['tris']}-triangle Desktop budget "
        "and was left unchanged.",
    }


def _reduced(
    collection_name: str,
    asset_class: str,
    budget: Mapping[str, int],
    names: Sequence[str],
    stats: Mapping[str, PartStats],
    targets: Mapping[str, int],
    finals: Mapping[str, int],
    settings: Mapping[str, Mapping[str, float]],
    shares: Mapping[str, float],
    paths: Mapping[str, Path],
    device: str,
    texture_px: int,
) -> dict[str, Any]:
    total_final = sum(finals[name] for name in names)
    total_source = sum(stats[name].tris for name in names)
    return {
        "kind": "reduce",
        "state": "reduced",
        "collection": collection_name,
        "asset_class": asset_class,
        "budget": budget["tris"],
        "parts": {
            name: {
                "source_tris": stats[name].tris,
                "target": targets[name],
                "final_tris": finals[name],
                "cage_extrusion": settings[name]["cage_extrusion"],
                "max_ray_distance": settings[name]["max_ray_distance"],
                "unbaked_share": round(float(shares[name]), 6),
            }
            for name in names
        },
        "total_tris": total_final,
        "textures": {kind: str(path) for kind, path in paths.items()},
        "texture_px": texture_px,
        "device": device,
        "summary": (
            f"Reduced {collection_name} from {total_source} to {total_final} triangles "
            f"(budget {budget['tris']}, {len(names)} part(s)), baked at {texture_px} px "
            f"on {device}."
        ),
    }


def _quiet(fraction: float, message: str) -> None:
    """The default progress sink: progress is not reported."""
