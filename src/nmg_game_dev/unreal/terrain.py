"""UE import for one exported terrain variant: a Landscape level per variant (#154, AC4, FR6).

``import_terrain_variant`` is the host entry point. It builds UE Python with ``build_terrain_code``,
runs it through an ``UnrealPythonClient``, and parses the ``NMG_RESULT`` line with
``import_asset.parse_nmg_result``. Pivot checks do not apply to terrain. The Landscape is checked
against the sidecar's sample heights instead.

The heightfield encoding is 16-bit, where 0 is the minimum height and 65535 the maximum. A flat
terrain encodes 32768. ``landscape_transform`` returns the Landscape location and scale in
centimetres that reproduce that encoding. ``ue_samples`` converts the Blender sample points to UE
centimetres with Y negated.

Import order for one variant, run inside the editor:

1. Import the ``T_<Name>_<L>_{BC,N,ORM}`` PNGs for every layer into ``dest``. The Height and Layer
   PNGs are never imported as textures. The texture settings match ``import_asset``.
2. Build ``M_<Name>_Landscape`` with ``NmgLandscapeLibrary.build_layered_material``, and one
   ``LI_<Name>_<L>`` layer info per layer with ``create_layer_info``.
3. Remember the open level, delete an existing ``L_<Name>``, and create ``L_<Name>`` in ``dest``.
4. ``NmgLandscapeLibrary.import_landscape`` at the derived transform. Then compare
   ``sample_heights`` with the sidecar's sample heights within 5 cm.
5. Save the level and restore the previous level in a ``finally``.

NMG_RESULT schema. The UE code prints exactly one ``NMG_RESULT {json}`` line, and it is always
printed, even on failure::

    {
      "ok": bool,
      "variant": "desktop"|"mobile",
      "name": "Terrain",
      "dest": "/Game/Terrain/Terrain/Desktop",
      "level": "/Game/Terrain/Terrain/Desktop/L_Terrain" | null,
      "material": "/Game/Terrain/Terrain/Desktop/M_Terrain_Landscape" | null,
      "layer_infos": ["/Game/.../LI_Terrain_Grass", ...],
      "textures": ["/Game/.../T_Terrain_Grass_BC", ...],
      "height_errors_cm": [0.2, ...],
      "error": null | "terrain_height_mismatch" | "ExceptionType: message"
    }
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final, cast

from nmg_game_dev.pipeline.errors import PipelineError

from .import_asset import UnrealPythonClient, parse_nmg_result
from .retry import RetrySettings, call_with_retry, retry_settings

_STAGE: Final = "import_ue"
_HEIGHT_ERROR: Final = "terrain_height_mismatch"
HEIGHT_TOLERANCE_CM: Final = 5.0
_CM_PER_METER: Final = 100.0
#: UE landscape heights: 16-bit, with the zero height at the midpoint 32768.
_HEIGHT_MAX: Final = 65535
_HEIGHT_MIDPOINT: Final = 32768
#: UE landscape Z is ``(height - 32768) / 128 * scale.z``.
_LANDSCAPE_Z_DIVISOR: Final = 128
_VARIANTS: Final = ("desktop", "mobile")
_TEXTURE_SUFFIXES: Final = ("BC", "N", "ORM")

_IMPORT_REMEDIATION: Final = (
    "Read the UE error in the message. Confirm the variant folder holds the T_<Name>_<Layer>_"
    "{BC,N,ORM} PNGs, the T_<Name>_Height.png heightmap, and the T_<Name>_Layer_<Layer>.png "
    "weightmaps, that the NmgGameDevEditor plugin with UNmgLandscapeLibrary is loaded, and that "
    "the editor is idle. Then rerun the import_ue step."
)
_HEIGHT_REMEDIATION: Final = (
    "The imported Landscape does not reproduce the Blender heightfield within 5 cm. Re-export the "
    "terrain and rerun import_ue. If the mismatch persists, check the heightmap encoding (0 is the "
    "minimum height, 65535 the maximum) and the Landscape Z scale and location from "
    "landscape_transform."
)

_TERRAIN_TEMPLATE: Final = r"""
import json
import os
import unreal

PARAMS = json.loads(__PARAMS__)
NAME = PARAMS["name"]
DEST = PARAMS["dest"]
LAYERS = PARAMS["layers"]
LEVEL_PATH = DEST + "/L_" + NAME
MATERIAL_NAME = "M_" + NAME + "_Landscape"
RESULT = {
    "ok": False,
    "variant": PARAMS["variant"],
    "name": NAME,
    "dest": DEST,
    "level": None,
    "material": None,
    "layer_infos": [],
    "textures": [],
    "height_errors_cm": [],
    "error": None,
}


class HeightMismatch(Exception):
    pass


def _file(name):
    path = os.path.join(PARAMS["variant_dir"], name)
    if not os.path.isfile(path):
        raise RuntimeError("file missing from the variant folder: " + path)
    return path


def _load(path):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if asset is None:
        raise RuntimeError("asset not found: " + path)
    return asset


def _texture_settings(texture, suffix):
    if suffix == "BC":
        texture.set_editor_property("srgb", True)
    elif suffix == "N":
        texture.set_editor_property("flip_green_channel", True)
        texture.set_editor_property(
            "compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP
        )
        texture.set_editor_property("srgb", False)
    else:
        texture.set_editor_property("srgb", False)
        texture.set_editor_property(
            "compression_settings", unreal.TextureCompressionSettings.TC_MASKS
        )


def _import_textures(tools):
    tasks = []
    stems = []
    for layer in LAYERS:
        for suffix in ("BC", "N", "ORM"):
            stem = "T_" + NAME + "_" + layer + "_" + suffix
            task = unreal.AssetImportTask()
            task.filename = _file(stem + ".png")
            task.destination_path = DEST
            task.destination_name = stem
            task.automated = True
            task.replace_existing = True
            task.save = True
            tasks.append(task)
            stems.append((layer, suffix, stem))
    tools.import_asset_tasks(tasks)
    textures = {}
    for layer, suffix, stem in stems:
        texture = _load(DEST + "/" + stem)
        _texture_settings(texture, suffix)
        unreal.EditorAssetLibrary.save_loaded_asset(texture)
        RESULT["textures"].append(DEST + "/" + stem)
        textures[(layer, suffix)] = texture
    return textures


def _open_level_path():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world is None:
        return None
    return world.get_path_name().split(".")[0]


def _delete_existing_level():
    if unreal.EditorAssetLibrary.does_asset_exist(LEVEL_PATH):
        if not unreal.EditorAssetLibrary.delete_asset(LEVEL_PATH):
            raise RuntimeError("could not delete the existing level " + LEVEL_PATH)


def _check_heights(landscape):
    expected = PARAMS["samples_cm"]
    points = [unreal.Vector2D(sample[0], sample[1]) for sample in expected]
    heights = unreal.NmgLandscapeLibrary.sample_heights(landscape, points)
    if len(heights) != len(expected):
        raise RuntimeError("sample_heights returned a different number of heights")
    errors = []
    uncovered = 0
    for sample, height in zip(expected, heights):
        value = float(height)
        if value != value:  # NaN: the Landscape does not cover this XY, so it cannot match
            uncovered += 1
            errors.append(None)
        else:
            errors.append(abs(value - sample[2]))
    RESULT["height_errors_cm"] = errors
    if uncovered:
        raise HeightMismatch(str(uncovered) + " sample point(s) lie outside the Landscape")
    if errors and max(errors) > PARAMS["tolerance_cm"]:
        raise HeightMismatch("sampled Landscape heights differ by up to " + str(max(errors)))


def _run():
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    textures = _import_textures(tools)
    material = unreal.NmgLandscapeLibrary.build_layered_material(
        DEST,
        MATERIAL_NAME,
        LAYERS,
        [textures[(layer, "BC")] for layer in LAYERS],
        [textures[(layer, "N")] for layer in LAYERS],
        [textures[(layer, "ORM")] for layer in LAYERS],
        PARAMS["mapping_scale"],
    )
    RESULT["material"] = DEST + "/" + MATERIAL_NAME
    layer_infos = []
    for layer in LAYERS:
        info_name = "LI_" + NAME + "_" + layer
        layer_infos.append(unreal.NmgLandscapeLibrary.create_layer_info(DEST, info_name, layer))
        RESULT["layer_infos"].append(DEST + "/" + info_name)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    previous = _open_level_path()
    opened = False
    try:
        _delete_existing_level()
        if not levels.new_level(LEVEL_PATH):
            raise RuntimeError("could not create the level " + LEVEL_PATH)
        opened = True
        RESULT["level"] = LEVEL_PATH
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        landscape = unreal.NmgLandscapeLibrary.import_landscape(
            world,
            _file(PARAMS["heightmap"]),
            [_file(name) for name in PARAMS["weightmaps"]],
            layer_infos,
            material,
            PARAMS["heightmap_px"],
            unreal.Vector(*PARAMS["location"]),
            unreal.Vector(*PARAMS["scale"]),
        )
        _check_heights(landscape)
    finally:
        if opened:
            levels.save_current_level()
        if previous is not None:
            levels.load_level(previous)
    RESULT["ok"] = True


try:
    _run()
except HeightMismatch:
    RESULT["error"] = "terrain_height_mismatch"
except Exception as error:
    RESULT["error"] = type(error).__name__ + ": " + str(error)
print("NMG_RESULT " + json.dumps(RESULT, sort_keys=True))
"""


def landscape_transform(
    n: int, spacing_m: float, zmin_m: float, zmax_m: float
) -> dict[str, list[float]]:
    """Return the Landscape ``location`` and ``scale`` in centimetres for one heightfield.

    ``n`` is the grid size per side, ``spacing_m`` the vertex spacing, and ``zmin_m``/``zmax_m``
    the world height range. The XY scale is the spacing. The Z scale maps the 16-bit range onto the
    height range. The location centres the grid on the origin and places the zero height at
    ``zmin_m``. A flat range (``zmax_m == zmin_m``) keeps Z scale 1.0 and places the terrain at
    ``zmin_m``.
    """
    if n < 2:
        raise ValueError(f"a heightfield needs at least 2 samples per side, got {n}")
    if spacing_m <= 0:
        raise ValueError(f"the vertex spacing must be positive, got {spacing_m}")
    if zmax_m < zmin_m:
        raise ValueError(f"the height range is inverted: {zmin_m} to {zmax_m}")
    cm_per_quad = spacing_m * _CM_PER_METER
    xy = -(n - 1) / 2 * cm_per_quad
    if zmax_m == zmin_m:
        scale_z = 1.0
        z = zmin_m * _CM_PER_METER
    else:
        scale_z = (zmax_m - zmin_m) * _CM_PER_METER * _LANDSCAPE_Z_DIVISOR / _HEIGHT_MAX
        z = zmin_m * _CM_PER_METER + _HEIGHT_MIDPOINT * scale_z / _LANDSCAPE_Z_DIVISOR
    return {"location": [xy, xy, z], "scale": [cm_per_quad, cm_per_quad, scale_z]}


def ue_samples(samples: Sequence[Sequence[float]]) -> list[list[float]]:
    """Convert Blender ``[x, y, z]`` metres to UE ``[x, y, z]`` centimetres (Y negated)."""
    return [[x * _CM_PER_METER, -y * _CM_PER_METER, z * _CM_PER_METER] for x, y, z in samples]


def build_terrain_code(
    variant_dir: str,
    dest: str,
    name: str,
    sidecar_variant: Mapping[str, Any],
) -> str:
    """Return the UE Python that imports one terrain variant into ``dest``.

    ``sidecar_variant`` is the variant's entry in ``nmg-variants.json`` (``desktop`` or ``mobile``),
    with ``heightmap_px``, ``spacing_m``, ``height_min_m``, ``height_max_m``, ``uv_tile_m``,
    ``layers``, and ``samples``. ``variant_dir`` holds the exported PNGs.
    """
    variant = _variant_of(dest)
    params = _terrain_params(variant, variant_dir, dest, name, sidecar_variant)
    return _TERRAIN_TEMPLATE.replace("__PARAMS__", json.dumps(json.dumps(params, sort_keys=True)))


def import_terrain_variant(
    client: UnrealPythonClient,
    *,
    variant_dir: str,
    dest: str,
    name: str,
    sidecar_variant: Mapping[str, Any],
    retry: RetrySettings | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Import one terrain variant through ``client`` and return the UE result.

    A timed-out request is retried with back-off, as for a mesh import (#149, FR6).  The result
    records ``attempts``.  Raises ``import_ue.terrain_height_mismatch`` when the sampled Landscape
    heights differ from the Blender heights by more than 5 cm. Any other failure raises
    ``import_ue.failed``.
    """
    try:
        code = build_terrain_code(variant_dir, dest, name, sidecar_variant)
    except ValueError as error:
        raise PipelineError(
            code="import_ue.failed",
            message=f"The terrain sidecar for {dest} is not usable: {error}",
            remediation="Re-export the terrain variant so nmg-variants.json holds its fields, then "
            "rerun the import_ue step.",
            stage=_STAGE,
        ) from error
    settings = retry if retry is not None else retry_settings()
    output, attempts = call_with_retry(
        client,
        code,
        retries=settings.retries,
        base_delay_s=settings.base_delay_s,
        sleep=sleep,
        clock=clock,
    )
    result = parse_nmg_result(output)
    if result.get("ok") is True:
        result["attempts"] = attempts
        return result
    if result.get("error") == _HEIGHT_ERROR:
        raise PipelineError(
            code="import_ue.terrain_height_mismatch",
            message=(
                f"The Landscape in {dest} differs from the Blender heightfield by up to "
                f"{_worst_error_cm(result):.2f} cm; the limit is {HEIGHT_TOLERANCE_CM:g} cm."
            ),
            remediation=_HEIGHT_REMEDIATION,
            stage=_STAGE,
        )
    error_text = result.get("error") or "UE reported no error text"
    raise PipelineError(
        code="import_ue.failed",
        message=f"UE import of {dest} failed: {error_text}",
        remediation=_IMPORT_REMEDIATION,
        stage=_STAGE,
    )


# --- helpers -----------------------------------------------------------------------------------


def _terrain_params(
    variant: str,
    variant_dir: str,
    dest: str,
    name: str,
    sidecar: Mapping[str, Any],
) -> dict[str, Any]:
    n = _int_field(sidecar, "heightmap_px")
    spacing = _float_field(sidecar, "spacing_m")
    zmin = _float_field(sidecar, "height_min_m")
    zmax = _float_field(sidecar, "height_max_m")
    uv_tile = _float_field(sidecar, "uv_tile_m")
    if spacing <= 0 or uv_tile <= 0:
        raise ValueError("spacing_m and uv_tile_m must be positive")
    layers = _layers(sidecar)
    transform = landscape_transform(n, spacing, zmin, zmax)
    return {
        "variant": variant,
        "variant_dir": variant_dir,
        "dest": dest,
        "name": name,
        "layers": layers,
        "heightmap": f"T_{name}_Height.png",
        "weightmaps": [f"T_{name}_Layer_{layer}.png" for layer in layers],
        "heightmap_px": n,
        "location": transform["location"],
        "scale": transform["scale"],
        "mapping_scale": uv_tile / spacing,
        "samples_cm": ue_samples(_samples(sidecar)),
        "tolerance_cm": HEIGHT_TOLERANCE_CM,
    }


def _variant_of(dest: str) -> str:
    leaf = dest.rstrip("/").rsplit("/", 1)[-1].lower()
    if leaf not in _VARIANTS:
        raise ValueError(f"terrain import destination must end in Desktop or Mobile: {dest}")
    return leaf


def _int_field(sidecar: Mapping[str, Any], key: str) -> int:
    value = sidecar.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"the terrain sidecar field {key} must be an integer")
    return value


def _float_field(sidecar: Mapping[str, Any], key: str) -> float:
    value = sidecar.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"the terrain sidecar field {key} must be a number")
    return float(value)


def _layers(sidecar: Mapping[str, Any]) -> list[str]:
    layers = sidecar.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ValueError("the terrain sidecar has no layers")
    names: list[str] = []
    for layer in cast(list[object], layers):
        if not isinstance(layer, str) or not layer:
            raise ValueError("every terrain layer must be a non-empty name")
        names.append(layer)
    return names


def _samples(sidecar: Mapping[str, Any]) -> list[list[float]]:
    samples = sidecar.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("the terrain sidecar has no height samples")
    points: list[list[float]] = []
    for sample in cast(list[object], samples):
        if not isinstance(sample, list) or len(sample) != 3:
            raise ValueError("every terrain height sample must be [x, y, z]")
        values: list[float] = []
        for value in cast(list[object], sample):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("every terrain height sample must hold numbers")
            values.append(float(value))
        points.append(values)
    return points


def _worst_error_cm(result: Mapping[str, Any]) -> float:
    errors = result.get("height_errors_cm")
    if not isinstance(errors, list) or not errors:
        return 0.0
    numbers = [float(item) for item in cast(list[object], errors) if isinstance(item, (int, float))]
    return max(numbers, default=0.0)


__all__ = [
    "HEIGHT_TOLERANCE_CM",
    "build_terrain_code",
    "import_terrain_variant",
    "landscape_transform",
    "ue_samples",
]
