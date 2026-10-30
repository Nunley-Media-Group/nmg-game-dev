"""bake_asset and run_for_mcp: the one implementation behind the operator, the Blender MCP call,
and the pipeline texture stage.

Order: validate budgets and materials, return a cache hit if nothing changed, render the pre-bake
proof, bake and pack the channels, retire the authored materials, rewire, render the post-bake
proof, and gate on its tolerance. A failure after the first mutation restores the file (state.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import bpy

from ..utils.budgets import BudgetOverrideError, resolve_budget
from . import bake, cache, pack, proof, rewire, tiling, uv
from .errors import BakeError
from .inspect import inspect_materials
from .state import BakeState


@dataclass
class _TextureSet:
    """One output set: the authored sources it covers and the float images it was baked into."""

    part: str
    sources: list[bpy.types.Material]
    source_names: list[str]
    images: dict[str, bpy.types.Image]
    paths: dict[str, dict[str, Path]] = field(default_factory=dict)


def bake_asset(
    collection: str,
    asset_class: str,
    out_dir: str | Path,
    budgets_path: str | Path | None = None,
    device: str = "GPU",
    samples: int = 32,
) -> dict[str, Any]:
    """Bake the collection's authored materials to contract textures. Returns the result dict.

    Raises BakeError (code texture.bake_failed) with a reason, a message naming the target, and a
    remediation. On a raised error the file is restored to its state before the call.
    """
    try:
        return _bake(collection, asset_class, Path(out_dir), budgets_path, device, samples)
    except BakeError:
        raise
    except Exception as exc:
        raise BakeError(
            "internal_error",
            f"Unexpected error while baking '{collection}': {exc}",
            target=collection,
        ) from exc


def run_for_mcp(**kwargs: Any) -> dict[str, Any]:
    """The MCP entry point: the result dict, or {"error": {...}} instead of raising."""
    try:
        return bake_asset(**kwargs)
    except BakeError as error:
        return {"error": error.as_dict()}


def _bake(
    collection_name: str,
    asset_class: str,
    out: Path,
    budgets_path: str | Path | None,
    device: str,
    samples: int,
) -> dict[str, Any]:
    collection = bpy.data.collections.get(collection_name)
    if collection is None:
        raise BakeError(
            "collection_missing",
            f"No collection named {collection_name} is in the open file.",
            target=collection_name,
        )
    desktop, mobile = _budgets(asset_class, budgets_path)
    desktop_px = desktop["max_texture_px"]
    mobile_px = mobile["max_texture_px"]
    mode = "tiling" if asset_class == "environment_piece" else "unique"
    meshes = sorted(
        (obj for obj in collection.all_objects if obj.type == "MESH"), key=lambda obj: obj.name
    )
    if not meshes:
        raise BakeError(
            "no_mesh",
            f"Collection {collection_name} has no mesh objects to bake.",
            target=collection_name,
        )
    sources = inspect_materials(meshes)
    merged = mode == "unique" and len(sources) > mobile["materials"]
    if mode == "tiling" and len(sources) > mobile["materials"]:
        raise BakeError(
            "material_limit",
            f"{collection_name} has {len(sources)} tiling materials; the {asset_class} Mobile "
            f"limit is {mobile['materials']}.",
            target=collection_name,
        )

    settings = {
        "asset_class": asset_class,
        "mode": mode,
        "budget": {"desktop": desktop, "mobile": mobile},
        "version": cache.BAKE_VERSION,
    }
    source_hash = cache.hash_asset(meshes, settings)
    manifest = cache.read_manifest(out)
    if cache.is_cache_hit(manifest, source_hash) and manifest is not None:
        return {**manifest, "cache_hit": True}

    names = rewire.part_names(sources, collection_name, merged)
    out.mkdir(parents=True, exist_ok=True)
    with BakeState(collection, meshes) as state:
        state.track_names(sources)
        state.make_render_enabled()
        device_used = bake.select_device(device)
        bake.configure(samples)
        frame = proof.frame_for(collection)
        pre_bake = out / f"{collection_name}_prebake.png"
        proof.render_three_quarter(collection, pre_bake, frame)
        bpy.ops.wm.save_as_mainfile(
            filepath=str(out / f"{collection_name}_prebake.blend"), copy=True
        )

        unwrapped = False
        if mode == "unique":
            groups = uv.faces_of(meshes, _source_map(meshes, sources, merged))
            if not uv.layout_is_valid(meshes, groups.values()):
                uv.joint_unwrap(meshes)
                unwrapped = True
            sets = _bake_unique(meshes, sources, names, merged, collection_name, desktop_px)
        else:
            uv.require_uv_layers(meshes)
            tiling.check_density(meshes, desktop_px, mobile_px)
            sets = _bake_tiling(sources, names, collection_name, desktop_px)

        for item in sets:
            _pack(item, collection_name, mode, out, desktop_px, mobile_px)
        for item in sets:
            for image in item.images.values():
                bpy.data.images.remove(image)

        if mode == "unique":
            if unwrapped:
                uv.finalize_unwrap(meshes)
        else:
            uv.finalize_tiling(meshes)

        rewire.retire(sources)
        replacements: dict[int, bpy.types.Material] = {}
        for item in sets:
            material = rewire.build_material(
                f"M_{collection_name}_{item.part}",
                collection_name,
                item.part,
                item.paths["desktop"],
            )
            for source in item.sources:
                replacements[source.as_pointer()] = material
        rewire.assign(meshes, replacements)
        if merged:
            body = replacements[sets[0].sources[0].as_pointer()]
            rewire.collapse(meshes, body)

        baked = out / f"{collection_name}_baked.png"
        proof.render_three_quarter(collection, baked, frame)
        metrics = proof.compare(pre_bake, baked)
        if not proof.within_tolerance(metrics):
            _discard_outputs(sets, out)
            raise BakeError(
                "proof_mismatch",
                f"The baked render of {collection_name} differs from the pre-bake render: mean "
                f"difference {metrics['mean_abs_diff']:.4f} (limit {proof.MEAN_TOLERANCE}), "
                f"outlier ratio {metrics['outlier_ratio']:.4f} (limit {proof.OUTLIER_TOLERANCE}). "
                f"Pre-bake: {pre_bake}; baked: {baked}.",
                target=collection_name,
            )
        baked_hash = cache.hash_asset(meshes, settings)
        result = _result(
            collection_name,
            asset_class,
            mode,
            merged,
            device_used,
            out,
            source_hash,
            baked_hash,
            desktop_px,
            mobile_px,
            sets,
            metrics,
            pre_bake,
            baked,
        )
    cache.write_manifest(out, result)
    return result


def _discard_outputs(sets: list[_TextureSet], out: Path) -> None:
    """Remove the PNGs and manifest a failed run wrote, so no stale cache entry survives.

    The run overwrote the previous outputs, so the old manifest no longer matches their content.
    Removing both makes the next run bake from the authored materials instead of hitting the cache.
    """
    for item in sets:
        for variant in item.paths.values():
            for path in variant.values():
                path.unlink(missing_ok=True)
    (out / cache.MANIFEST).unlink(missing_ok=True)


def _budgets(
    asset_class: str, budgets_path: str | Path | None
) -> tuple[dict[str, int], dict[str, int]]:
    path = budgets_path or None
    try:
        desktop = resolve_budget(asset_class, path, "desktop")
        mobile = resolve_budget(asset_class, path, "mobile")
    except BudgetOverrideError as error:
        raise BakeError(
            "budget_invalid",
            error.message,
            target=asset_class,
            remediation=error.remediation,
        ) from error
    for label, budget in (("Desktop", desktop), ("Mobile", mobile)):
        size = budget["max_texture_px"]
        if size <= 0 or size & (size - 1):
            raise BakeError(
                "budget_invalid",
                f"{label} texture size {size} for {asset_class} is not a power of two.",
                target=asset_class,
            )
    return desktop, mobile


def _source_map(
    meshes: list[bpy.types.Object], sources: list[bpy.types.Material], merged: bool
) -> dict[str, list[int]]:
    """For each mesh, the source index behind each slot (all zero when merging)."""
    index_of = {source.as_pointer(): index for index, source in enumerate(sources)}
    return {
        obj.name: [
            0 if merged else index_of[slot.material.as_pointer()] for slot in obj.material_slots
        ]
        for obj in meshes
    }


def _bake_unique(
    meshes: list[bpy.types.Object],
    sources: list[bpy.types.Material],
    names: list[str],
    merged: bool,
    asset: str,
    size: int,
) -> list[_TextureSet]:
    """Bake every channel. One atlas when merged, otherwise one set per authored material."""
    if merged:
        images = {
            channel: bake.new_channel_image(f"__nmg_{asset}_Body_{channel}", size)
            for channel in bake.CHANNELS
        }
        for channel in bake.CHANNELS:
            bake.bake_channel(meshes, sources, [images[channel]] * len(sources), channel, size)
        return [_TextureSet("Body", list(sources), [s.name for s in sources], images)]
    per_source = [
        {
            channel: bake.new_channel_image(f"__nmg_{asset}_{part}_{channel}", size)
            for channel in bake.CHANNELS
        }
        for part in names
    ]
    for channel in bake.CHANNELS:
        bake.bake_channel(
            meshes, sources, [images[channel] for images in per_source], channel, size
        )
    return [
        _TextureSet(part, [source], [source.name], images)
        for part, source, images in zip(names, sources, per_source, strict=True)
    ]


def _bake_tiling(
    sources: list[bpy.types.Material], names: list[str], asset: str, size: int
) -> list[_TextureSet]:
    """Bake each tiling material on its own 1 m tile, so the image is one UV period."""
    sets: list[_TextureSet] = []
    for part, source in zip(names, sources, strict=True):
        tile = tiling.make_tile()
        mesh = tile.data
        mesh.materials.append(source)
        try:
            images = {
                channel: bake.new_channel_image(f"__nmg_{asset}_{part}_{channel}", size)
                for channel in bake.CHANNELS
            }
            for channel in bake.CHANNELS:
                bake.bake_channel([tile], [source], [images[channel]], channel, size)
        finally:
            bpy.data.objects.remove(tile, do_unlink=True)
            bpy.data.meshes.remove(mesh)
        sets.append(_TextureSet(part, [source], [source.name], images))
    return sets


def _pack(
    item: _TextureSet,
    asset: str,
    mode: str,
    out: Path,
    desktop_px: int,
    mobile_px: int,
) -> None:
    rgba = {channel: pack.read_rgba(image) for channel, image in item.images.items()}
    channels = {
        "BC": pack.base_color_rgb(rgba["BC"]),
        "N": pack.normal_rgb(rgba["N"]),
        "ORM": pack.orm_rgb(rgba["AO"], rgba["ROUGH"], rgba["METAL"]),
    }
    if mode == "tiling":
        tiling.check_seams(item.source_names[0], channels)
    item.paths = pack.pack_set(
        item.part,
        asset,
        channels,
        out / "Desktop",
        out / "Mobile",
        desktop_px,
        mobile_px,
    )


def _result(
    asset: str,
    asset_class: str,
    mode: str,
    merged: bool,
    device: str,
    out: Path,
    source_hash: str,
    baked_hash: str,
    desktop_px: int,
    mobile_px: int,
    sets: list[_TextureSet],
    metrics: dict[str, float],
    pre_bake: Path,
    baked: Path,
) -> dict[str, Any]:
    desktop_paths = [path for item in sets for path in item.paths["desktop"].values()]
    mobile_paths = [path for item in sets for path in item.paths["mobile"].values()]
    count = len(sets)
    return {
        "kind": "bake",
        "asset": asset,
        "class": asset_class,
        "mode": mode,
        "merged": merged,
        "cache_hit": False,
        "device": device,
        "manifest_path": str(out / cache.MANIFEST),
        "source_hash": source_hash,
        "baked_hash": baked_hash,
        "desktop_dir": str(out / "Desktop"),
        "mobile_dir": str(out / "Mobile"),
        "desktop_px": desktop_px,
        "mobile_px": mobile_px,
        "materials": [
            {
                "name": f"M_{asset}_{item.part}",
                "source": item.source_names,
                "desktop": {kind: str(path) for kind, path in item.paths["desktop"].items()},
                "mobile": {kind: str(path) for kind, path in item.paths["mobile"].items()},
            }
            for item in sets
        ],
        "desktop_textures": sorted(str(path) for path in desktop_paths),
        "mobile_textures": sorted(str(path) for path in mobile_paths),
        "texture_bytes_desktop": pack.file_bytes(desktop_paths),
        "texture_bytes_mobile": pack.file_bytes(mobile_paths),
        "proof": {
            "pre_bake": str(pre_bake),
            "baked": str(baked),
            "mean_abs_diff": round(metrics["mean_abs_diff"], 6),
            "outlier_ratio": round(metrics["outlier_ratio"], 6),
        },
        "summary": (
            f"Baked {count} material{'s' if count != 1 else ''} for {asset} ({asset_class}): "
            f"Desktop {desktop_px} px, Mobile {mobile_px} px, proof diff "
            f"{metrics['mean_abs_diff']:.3f}"
        ),
    }
