"""UE import for one finalized variant, run through the Unreal MCP ``execute_python_code`` (#69).

``import_variant`` is the host entry point for one variant folder. It builds UE Python with
``build_import_code``, runs it through an ``UnrealPythonClient`` (``UnrealMcpClient`` in
production), parses the result, and compares child-part pivots with ``check_pivots``.

Import order for one variant, run inside the editor:

1. Import every ``T_*.png`` into ``dest`` (``AssetImportTask(automated=True,
   replace_existing=True, save=True)``). ``_BC`` is sRGB. ``_N`` has flip green channel, normal
   compression, and linear color. ``_ORM`` is linear with masks compression.
2. Import ``SM_<Name>.fbx`` with materials, textures, and skeletal import off, and with
   ``combine_meshes``, ``transform_vertex_to_absolute``, and ``bake_pivot_in_vertex`` all off.
   Each mesh node becomes its own static mesh.
3. For each static mesh material slot named ``M_<Name>_<Part>``, create or reuse
   ``MI_<Name>_<Part>`` in ``dest``. Parent it to ``/nmg-game-dev/Materials/M_NmgORM`` and set
   ``BaseColor``, ``Normal``, and ``ORM`` from ``T_<Name>_<Part>_{BC,N,ORM}``. Assign it to the
   slot and save.
4. Report each static mesh's local bounds.

NMG_RESULT schema. The UE code prints exactly one ``NMG_RESULT {json}`` line, and it is always
printed, even on failure::

    {
      "ok": bool,                   # true only when every step above finished
      "variant": "desktop"|"mobile", # the dest folder, lower-cased; matches snapshot "variant"
      "name": "Crate",
      "dest": "/Game/Props/Crate/Desktop",
      "textures": ["/Game/.../T_Crate_Body_BC", ...],
      "materials": {"M_Crate_Body": "/Game/.../MI_Crate_Body"},
      "static_meshes": {
        "SM_Crate_Body": {"path": "/Game/.../SM_Crate_Body",
                          "bounds": {"min": [x, y, z], "max": [x, y, z]}}   # cm, UE axes, local
      },
      "error": null | "ExceptionType: message"
    }

Pivot check. ``check_pivots`` compares each snapshot ``MESH`` entry of the variant with its UE
static mesh. The snapshot key is the Blender object name. The UE static mesh is matched by the
same key, or by the key with ``_Mobile`` removed (the export name). Blender meters are converted
to centimeters, and Y is negated, which swaps the Y extremes. Each component must match within
0.01 cm. The snapshot entry must carry ``local_bounds``: ``{"min": [x, y, z], "max": [x, y, z]}``
in Blender meters, object-local space. Without it the check cannot run, so it fails closed with
``import_ue.pivot_mismatch``.
"""

from __future__ import annotations

import json
import math
from typing import Any, Final, NoReturn, Protocol, cast

from nmg_game_dev.pipeline.errors import PipelineError

_STAGE: Final = "import_ue"
_RESULT_PREFIX: Final = "NMG_RESULT "
#: Matches ``contract_core.validate.MOBILE_SUFFIX``; the Mobile export name drops it.
_MOBILE_SUFFIX: Final = "_Mobile"
PIVOT_TOLERANCE_CM: Final = 0.01
_CM_PER_METER: Final = 100.0
_MASTER_PATH: Final = "/nmg-game-dev/Materials/M_NmgORM"
_VARIANTS: Final = ("desktop", "mobile")

_IMPORT_REMEDIATION: Final = (
    "Read the UE error in the message. Confirm the variant folder holds the FBX and the T_*.png "
    "textures, that scripts/unreal/build_master_material.py has built M_NmgORM, and that the "
    "editor is idle, then rerun the import_ue step."
)
_PIVOT_REMEDIATION: Final = (
    "The imported static mesh no longer matches the Blender part. Re-export the variant and "
    "rerun import_ue. If the mismatch persists, check the part pivot in Blender (object origin "
    "in object-local space) and the export options."
)

_IMPORT_TEMPLATE: Final = r"""
import json
import os
import unreal

PARAMS = json.loads(__PARAMS__)
MASTER_PATH = "/nmg-game-dev/Materials/M_NmgORM"
RESULT = {
    "ok": False,
    "variant": PARAMS["variant"],
    "name": PARAMS["name"],
    "dest": PARAMS["dest"],
    "textures": [],
    "materials": {},
    "static_meshes": {},
    "error": None,
}


def _load(path):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if asset is None:
        raise RuntimeError("asset not found: " + path)
    return asset


def _import_textures(tools):
    dest = PARAMS["dest"]
    stems = sorted(
        os.path.splitext(name)[0]
        for name in os.listdir(PARAMS["variant_dir"])
        if name.startswith("T_") and name.lower().endswith(".png")
    )
    tasks = []
    for stem in stems:
        task = unreal.AssetImportTask()
        task.filename = os.path.join(PARAMS["variant_dir"], stem + ".png")
        task.destination_path = dest
        task.destination_name = stem
        task.automated = True
        task.replace_existing = True
        task.save = True
        tasks.append(task)
    if tasks:
        tools.import_asset_tasks(tasks)
    for stem in stems:
        suffix = stem.rsplit("_", 1)[-1]
        texture = _load(dest + "/" + stem)
        if suffix == "BC":
            texture.set_editor_property("srgb", True)
        elif suffix == "N":
            texture.set_editor_property("flip_green_channel", True)
            texture.set_editor_property(
                "compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP
            )
            texture.set_editor_property("srgb", False)
        elif suffix == "ORM":
            texture.set_editor_property("srgb", False)
            texture.set_editor_property(
                "compression_settings", unreal.TextureCompressionSettings.TC_MASKS
            )
        else:
            raise RuntimeError("texture has no BC, N, or ORM suffix: " + stem)
        unreal.EditorAssetLibrary.save_loaded_asset(texture)
        RESULT["textures"].append(dest + "/" + stem)


def _import_meshes(tools):
    fbx = os.path.join(PARAMS["variant_dir"], "SM_" + PARAMS["name"] + ".fbx")
    if not os.path.isfile(fbx):
        raise RuntimeError("FBX missing from the variant folder: " + fbx)
    options = unreal.FbxImportUI()
    options.import_materials = False
    options.import_textures = False
    options.import_as_skeletal = False
    options.static_mesh_import_data.combine_meshes = False
    options.static_mesh_import_data.transform_vertex_to_absolute = False
    options.static_mesh_import_data.bake_pivot_in_vertex = False
    task = unreal.AssetImportTask()
    task.filename = fbx
    task.destination_path = PARAMS["dest"]
    task.automated = True
    task.replace_existing = True
    task.save = True
    task.options = options
    tools.import_asset_tasks([task])
    meshes = []
    for object_path in sorted({path.split(".")[0] for path in task.imported_object_paths}):
        asset = unreal.EditorAssetLibrary.load_asset(object_path)
        if isinstance(asset, unreal.StaticMesh):
            meshes.append((object_path, asset))
    if not meshes:
        raise RuntimeError("the FBX imported no static meshes: " + fbx)
    return meshes


def _bounds(mesh):
    box = mesh.get_bounding_box()
    return {
        "min": [box.min.x, box.min.y, box.min.z],
        "max": [box.max.x, box.max.y, box.max.z],
    }


def _check_expected(meshes):
    names = {path.rsplit("/", 1)[-1] for path, _ in meshes}
    for candidates in PARAMS["expected_meshes"]:
        if not any(candidate in names for candidate in candidates):
            raise RuntimeError("no static mesh for snapshot part: " + candidates[0])


def _instance(tools, dest, name, parent):
    path = dest + "/" + name
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        instance = _load(path)
    else:
        instance = tools.create_asset(
            name, dest, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew()
        )
    if instance is None:
        raise RuntimeError("could not create material instance: " + path)
    unreal.MaterialEditingLibrary.set_material_instance_parent(instance, parent)
    return instance


def _bind_materials(tools, meshes):
    parent = unreal.EditorAssetLibrary.load_asset(MASTER_PATH)
    if parent is None:
        raise RuntimeError("M_NmgORM is missing; run scripts/unreal/build_master_material.py")
    dest = PARAMS["dest"]
    name = PARAMS["name"]
    prefix = "M_" + name + "_"
    for object_path, mesh in meshes:
        mesh_name = object_path.rsplit("/", 1)[-1]
        RESULT["static_meshes"][mesh_name] = {"path": object_path, "bounds": _bounds(mesh)}
        for index, slot in enumerate(mesh.static_materials):
            slot_name = str(slot.material_slot_name)
            if not slot_name.startswith(prefix):
                raise RuntimeError(
                    "material slot " + slot_name + " on " + mesh_name + " is not M_<Name>_<Part>"
                )
            part = slot_name[len(prefix) :]
            instance = _instance(tools, dest, "MI_" + name + "_" + part, parent)
            for parameter, suffix in (("BaseColor", "BC"), ("Normal", "N"), ("ORM", "ORM")):
                texture_path = dest + "/T_" + name + "_" + part + "_" + suffix
                texture = unreal.EditorAssetLibrary.load_asset(texture_path)
                if texture is None:
                    raise RuntimeError("texture missing: " + texture_path)
                unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(
                    instance, parameter, texture
                )
            unreal.EditorAssetLibrary.save_loaded_asset(instance)
            mesh.set_material(index, instance)
            RESULT["materials"][slot_name] = dest + "/MI_" + name + "_" + part
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)


def _run():
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    _import_textures(tools)
    meshes = _import_meshes(tools)
    _check_expected(meshes)
    _bind_materials(tools, meshes)
    RESULT["ok"] = True


try:
    _run()
except Exception as error:
    RESULT["error"] = type(error).__name__ + ": " + str(error)
print("NMG_RESULT " + json.dumps(RESULT, sort_keys=True))
"""


class UnrealPythonClient(Protocol):
    """The one client surface the import needs. ``UnrealMcpClient`` and test fakes satisfy it."""

    def execute_python_code(self, code: str) -> str:
        """Run UE Python in the editor and return the tool's text output."""
        ...


def build_import_code(
    variant_dir: str,
    dest: str,
    name: str,
    report: dict[str, Any],
) -> str:
    """Return the UE Python that imports one variant folder into ``dest``.

    ``report`` is the pre-export contract report. Its snapshot tells the UE side which
    ``MESH`` parts of this variant must come back as static meshes, so a missing part fails
    before any material is bound.
    """
    variant = _variant_of(dest)
    params: dict[str, Any] = {
        "variant": variant,
        "variant_dir": variant_dir,
        "dest": dest,
        "name": name,
        "expected_meshes": _expected_mesh_candidates(report, variant),
    }
    return _IMPORT_TEMPLATE.replace("__PARAMS__", json.dumps(json.dumps(params, sort_keys=True)))


def parse_nmg_result(output: str) -> dict[str, Any]:
    """Return the last ``NMG_RESULT {json}`` object in the MCP tool output.

    VibeUE wraps the UE log in a JSON envelope whose ``output`` field holds the printed text, so
    the envelope is decoded first. An envelope with ``success`` false raises ``import_ue.failed``.
    """
    envelope = _envelope(output)
    if envelope is not None and envelope.get("success") is False:
        _fail_import(f"UE Python reported failure: {_envelope_error(envelope)}")
    for text in _candidate_texts(output, envelope):
        for line in reversed(text.splitlines()):
            stripped = line.strip()
            if not stripped.startswith(_RESULT_PREFIX):
                continue
            try:
                decoded: Any = json.loads(stripped[len(_RESULT_PREFIX) :])
            except json.JSONDecodeError as error:
                _fail_import(f"NMG_RESULT line is not valid JSON: {error}")
            if isinstance(decoded, dict):
                return cast(dict[str, Any], decoded)
    _fail_import("UE Python printed no NMG_RESULT line; the import did not report a result")


def check_pivots(report: dict[str, Any], result: dict[str, Any]) -> None:
    """Compare each child part's local bounds with the pre-export snapshot, within 0.01 cm.

    Raises ``import_ue.pivot_mismatch`` on any mismatch, on a part with no static mesh, or on a
    snapshot part that has no ``local_bounds``.
    """
    variant = str(result.get("variant", ""))
    snapshot = report.get("snapshot")
    measured = result.get("static_meshes")
    if not isinstance(snapshot, dict) or not isinstance(measured, dict):
        _fail_pivot("the report or the UE result has no snapshot or static_meshes")
    for key in sorted(snapshot):
        entry = snapshot[key]
        if not isinstance(entry, dict) or entry.get("type") != "MESH":
            continue
        if entry.get("variant") != variant:
            continue
        mesh_name = _matching_mesh(key, measured)
        if mesh_name is None:
            _fail_pivot(f"no static mesh was imported for snapshot part {key}")
        expected = _expected_bounds_cm(key, entry)
        actual_entry = measured[mesh_name]
        actual = actual_entry.get("bounds") if isinstance(actual_entry, dict) else None
        if not isinstance(actual, dict):
            _fail_pivot(f"static mesh {mesh_name} reported no bounds")
        for corner in ("min", "max"):
            _compare_corner(key, mesh_name, corner, expected[corner], actual.get(corner))


def import_variant(
    client: UnrealPythonClient,
    *,
    variant_dir: str,
    dest: str,
    name: str,
    report: dict[str, Any],
) -> dict[str, Any]:
    """Import one variant through ``client``, then check its pivots. Return the UE result."""
    code = build_import_code(variant_dir, dest, name, report)
    result = parse_nmg_result(client.execute_python_code(code))
    if result.get("ok") is not True:
        error_text = result.get("error") or "UE reported no error text"
        raise PipelineError(
            code="import_ue.failed",
            message=f"UE import of {dest} failed: {error_text}",
            remediation=_IMPORT_REMEDIATION,
            stage=_STAGE,
        )
    check_pivots(report, result)
    return result


# --- helpers -----------------------------------------------------------------------------------


def _variant_of(dest: str) -> str:
    leaf = dest.rstrip("/").rsplit("/", 1)[-1].lower()
    if leaf not in _VARIANTS:
        raise ValueError(f"import destination must end in Desktop or Mobile: {dest}")
    return leaf


def _export_name(key: str) -> str:
    return key.replace(_MOBILE_SUFFIX, "", 1)


def _expected_mesh_candidates(report: dict[str, Any], variant: str) -> list[list[str]]:
    snapshot = report.get("snapshot")
    if not isinstance(snapshot, dict):
        return []
    candidates: list[list[str]] = []
    for key in sorted(snapshot):
        entry = snapshot[key]
        if (
            isinstance(entry, dict)
            and entry.get("type") == "MESH"
            and entry.get("variant") == variant
        ):
            candidates.append(sorted({key, _export_name(key)}))
    return candidates


def _matching_mesh(key: str, measured: dict[str, Any]) -> str | None:
    for candidate in (key, _export_name(key)):
        if candidate in measured:
            return candidate
    return None


def _expected_bounds_cm(key: str, entry: dict[str, Any]) -> dict[str, list[float]]:
    local = entry.get("local_bounds")
    if not isinstance(local, dict):
        _fail_pivot(
            f"snapshot part {key} has no local_bounds, so its pivot cannot be verified. Add the "
            "object-local bounding box to the contract snapshot"
        )
    low = _vector(local.get("min"))
    high = _vector(local.get("max"))
    if low is None or high is None:
        _fail_pivot(f"snapshot part {key} has malformed local_bounds")
    # Meters to centimeters. Negating Y swaps the Y extremes, so min and max trade places there.
    return {
        "min": [low[0] * _CM_PER_METER, -high[1] * _CM_PER_METER, low[2] * _CM_PER_METER],
        "max": [high[0] * _CM_PER_METER, -low[1] * _CM_PER_METER, high[2] * _CM_PER_METER],
    }


def _compare_corner(
    key: str,
    mesh_name: str,
    corner: str,
    expected: list[float],
    actual: object,
) -> None:
    if not isinstance(actual, list) or len(actual) != 3:
        _fail_pivot(f"static mesh {mesh_name} reported malformed {corner} bounds")
    values = [_number(value) for value in actual]
    for axis, (want, got) in enumerate(zip(expected, values, strict=True)):
        if got is None or not math.isclose(want, got, rel_tol=0.0, abs_tol=PIVOT_TOLERANCE_CM):
            shown = "missing" if got is None else f"{got:.4f}"
            _fail_pivot(
                f"{mesh_name} ({key}) {corner} on axis {axis} is {shown} cm; the Blender part "
                f"expects {want:.4f} cm within {PIVOT_TOLERANCE_CM} cm"
            )


def _vector(value: object) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 3:
        return None
    numbers = [_number(item) for item in value]
    if any(number is None for number in numbers):
        return None
    return [cast(float, number) for number in numbers]


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _envelope(output: str) -> dict[str, Any] | None:
    try:
        decoded: Any = json.loads(output)
    except json.JSONDecodeError:
        return None
    return cast(dict[str, Any], decoded) if isinstance(decoded, dict) else None


def _candidate_texts(output: str, envelope: dict[str, Any] | None) -> list[str]:
    if envelope is None:
        return [output]
    texts = [output]
    stack: list[object] = list(envelope.values())
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict):
            stack.extend(cast(dict[str, object], item).values())
        elif isinstance(item, list):
            stack.extend(cast(list[object], item))
    return texts


def _envelope_error(envelope: dict[str, Any]) -> str:
    for key in ("error", "message", "output"):
        value = envelope.get(key)
        if isinstance(value, str) and value:
            return value[:500]
    return "no error text"


def _fail_import(message: str) -> NoReturn:
    raise PipelineError(
        code="import_ue.failed",
        message=message,
        remediation=_IMPORT_REMEDIATION,
        stage=_STAGE,
    )


def _fail_pivot(message: str) -> NoReturn:
    raise PipelineError(
        code="import_ue.pivot_mismatch",
        message=message,
        remediation=_PIVOT_REMEDIATION,
        stage=_STAGE,
    )


__all__ = [
    "PIVOT_TOLERANCE_CM",
    "UnrealPythonClient",
    "build_import_code",
    "check_pivots",
    "import_variant",
    "parse_nmg_result",
]
