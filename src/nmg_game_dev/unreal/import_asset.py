"""UE import for one finalized variant, run through the Unreal MCP ``execute_python_code`` (#69).

``import_variant`` is the host entry point for one variant folder. It builds UE Python with
``build_import_code``, runs it through an ``UnrealPythonClient`` (``UnrealMcpClient`` in
production), parses the result, and compares child-part pivots with ``check_pivots``.

Import order for one variant, run inside the editor:

1. Import every ``T_*.png`` into ``dest`` (``AssetImportTask(automated=True,
   replace_existing=True, save=True)``). ``_BC`` is sRGB. ``_N`` has flip green channel, normal
   compression, and linear color. ``_ORM`` is linear with masks compression.
2. Import ``SM_<Name>.fbx``. A static asset imports with materials, textures, and skeletal import
   off, and with ``combine_meshes`` and ``bake_pivot_in_vertex`` off. Each mesh node becomes its
   own static mesh. The static import splits on the part count (#145):

   - Single-part: ``transform_vertex_to_absolute`` is on. The one part sits at the asset origin,
     so baking the node transform applies the FBX unit conversion without moving a pivot, and UE
     names the mesh after the node (the Blender object).
   - Multi-part: ``transform_vertex_to_absolute`` is off, so every part keeps its own pivot. Under
     Interchange the unit conversion sits on the node transform, not the vertices, so each mesh
     would stay at 1/100 of its authored size. Every LOD of every static mesh then gets
     ``build_scale3d`` 100 through ``StaticMeshEditorSubsystem`` and is saved, which rebuilds its
     bounds in centimetres. A mesh is named after its datablock, so each one whose datablock is
     mapped to a part is renamed to that part's export name, consolidating an existing asset at
     that name first so references follow the new mesh.

   This replaces the ghost1 ``sitecustomize.py`` workaround (its ``_IMPORT_TEMPLATE`` patch in
   ``Tools/nmgpatch``), which applied the same two steps in process. The workaround wrote the
   scale only while it was still 1.0, so a reimport over a mesh already at scale 100 kept stale
   bounds. The write here is absolute and always rebuilds.

   A rigged asset (its snapshot holds the armature ``SK_<Name>``) imports as a Skeletal Mesh and
   runs neither the build-scale nor the rename step.
   UE 5.8 lists only the first mesh of a multi-part FBX in ``task.imported_object_paths`` (#141),
   so the code never reads that list. Each expected mesh is found by name in ``dest``: each name
   in its snapshot entry's candidate list is tried as ``dest/<name>``, and the first that is an
   asset of the expected class wins. A multi-part import finds its parts by datablock name, scales
   and renames them as above, then resolves the expected names, so a renamed part is found under
   its export name. Other assets in the folder are never bound or reported.

   The Desktop variant creates ``SM_<Name>_Skeleton`` and ``SM_<Name>_PhysicsAsset`` in ``dest``.
   The import must make the skeleton, or it fails. When the import did not make the physics asset,
   the code creates it with ``SkeletalMeshEditorSubsystem.create_physics_asset``, moves it to
   ``dest/SM_<Name>_PhysicsAsset`` if UE placed it elsewhere, assigns it, and saves both (#141).
   The Mobile variant reuses those two from ``skeleton_dest`` and imports
   ``SM_<Name>_LOD1.fbx`` and ``SM_<Name>_LOD2.fbx`` as LOD 1 and 2 with
   ``SkeletalMeshEditorSubsystem.import_lod``.

   A static LOD group (a non-rigged variant whose snapshot holds ``SM_<Name>_Mobile_LOD0``,
   ``_LOD1``, and ``_LOD2``, #146) imports as one Static Mesh ``SM_<Name>``. Interchange builds it
   from the LOD-group FBX, with the exported LOD meshes as its LODs, so the code reads no LOD
   import option and makes no separate LOD import. The group is single-part, so the single-part
   options above apply, and the build-scale and rename steps do not run.
3. For each mesh material slot named ``M_<Name>_<Part>``, create or reuse
   ``MI_<Name>_<Part>`` in ``dest``. Parent it to ``/nmg-game-dev/Materials/M_NmgORM`` and set
   ``BaseColor``, ``Normal``, and ``ORM`` from ``T_<Name>_<Part>_{BC,N,ORM}``. Assign it to the
   slot and save.
4. Report each mesh's local bounds.

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
                          "bounds": {"min": [x, y, z], "max": [x, y, z]},   # cm, UE axes, local
                          "lod_count": 1}                                    # get_num_lods()
      },
      "skeletal_meshes": {                                       # rigged variants only
        "SM_Hero": {"path": "/Game/.../SM_Hero",
                    "bounds": {"min": [x, y, z], "max": [x, y, z]},
                    "lod_count": 3,
                    "skeleton": "/Game/.../SM_Hero_Skeleton",
                    "physics_asset": "/Game/.../SM_Hero_PhysicsAsset"}
      },
      "error": null | "ExceptionType: message"
    }

Pivot check. ``check_pivots`` compares each snapshot ``MESH`` entry of the variant with its UE
mesh, static or skeletal. The snapshot key is the Blender object name. The UE mesh is matched by
the same key, or by the key with ``_Mobile`` removed (the export name). A rigged asset's
``_LOD1``/``_LOD2`` entries are not compared, because they are LODs of the root Skeletal Mesh. A
static LOD group's ``_LOD0`` entry is compared with the Static Mesh ``SM_<Name>``, and its
``_LOD1``/``_LOD2`` entries are not compared either. Blender meters are converted to centimeters,
and Y is negated, which swaps the Y extremes. Each component must match within 0.01 cm. The
snapshot entry must carry ``local_bounds``: ``{"min": [x, y, z], "max": [x, y, z]}`` in Blender
meters, object-local space. Without it the check cannot run, so it fails closed with
``import_ue.pivot_mismatch``.

LOD count check. ``check_lod_counts`` runs before the pivot check. For each static LOD group it
requires the Static Mesh's ``lod_count`` to equal the group's number of LOD objects. A mismatch,
or a missing count, fails with ``import_ue.failed`` that names the mesh and both counts.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from collections.abc import Callable
from typing import Any, Final, NoReturn, Protocol, cast

from nmg_game_dev.pipeline.errors import PipelineError

from .retry import RetrySettings, call_with_retry, retry_settings

_STAGE: Final = "import_ue"
_RESULT_PREFIX: Final = "NMG_RESULT "
#: Matches ``contract_core.validate.MOBILE_SUFFIX``; the Mobile export name drops it.
_MOBILE_SUFFIX: Final = "_Mobile"
#: Matches ``contract_core.validate._LOD_EXTRA``: LOD1 and LOD2 objects of a rigged Mobile variant
#: or of a static LOD group, which UE gives no mesh of their own (#146).
_LOD_EXTRA: Final = re.compile(r"_LOD[1-9]$")
_LOD0_SUFFIX: Final = "_LOD0"
#: Any LOD suffix, with its level captured. A multi-part count treats ``SM_Crate_LOD0`` and
#: ``SM_Crate`` as one part.
_LOD_ANY: Final = re.compile(r"_LOD([0-9]+)$")
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
CM_PER_METER = 100.0
ASSET_NAME_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
RESULT = {
    "ok": False,
    "variant": PARAMS["variant"],
    "name": PARAMS["name"],
    "dest": PARAMS["dest"],
    "textures": [],
    "materials": {},
    "static_meshes": {},
    "skeletal_meshes": {},
    "error": None,
}
LOD_COUNT = {}


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


def _static_options():
    options = unreal.FbxImportUI()
    options.import_materials = False
    options.import_textures = False
    options.import_as_skeletal = False
    options.static_mesh_import_data.combine_meshes = False
    options.static_mesh_import_data.transform_vertex_to_absolute = not PARAMS["multi_part"]
    options.static_mesh_import_data.bake_pivot_in_vertex = False
    return options


def _skeleton_path():
    return PARAMS["skeleton_dest"] + "/SM_" + PARAMS["name"] + "_Skeleton"


def _physics_path():
    return PARAMS["skeleton_dest"] + "/SM_" + PARAMS["name"] + "_PhysicsAsset"


def _skeletal_options(desktop):
    options = unreal.FbxImportUI()
    options.import_materials = False
    options.import_textures = False
    options.import_as_skeletal = True
    options.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH
    options.import_animations = False
    if desktop:
        options.create_physics_asset = True
    else:
        options.create_physics_asset = False
        options.skeleton = _load(_skeleton_path())
        options.physics_asset = _load(_physics_path())
    return options


def _import_fbx(tools, fbx, options):
    task = unreal.AssetImportTask()
    task.filename = fbx
    task.destination_path = PARAMS["dest"]
    task.automated = True
    task.replace_existing = True
    task.save = True
    task.options = options
    tools.import_asset_tasks([task])


def _resolve_expected(asset_class):
    # Each expected mesh is looked up by name in dest, never read from the import task: UE 5.8
    # lists only the first mesh of a multi-part FBX there (#141). A part with no match is collected,
    # so one error names every missing part.
    dest = PARAMS["dest"]
    found = []
    seen = set()
    missing = []
    for candidates in PARAMS["expected_meshes"]:
        match = None
        for name in candidates:
            path = dest + "/" + name
            if not unreal.EditorAssetLibrary.does_asset_exist(path):
                continue
            asset = unreal.EditorAssetLibrary.load_asset(path)
            if isinstance(asset, asset_class):
                match = (path, asset)
                break
        if match is None:
            missing.append(candidates[0])
        elif match[0] not in seen:
            seen.add(match[0])
            found.append(match)
    if missing:
        kind = "skeletal" if asset_class is unreal.SkeletalMesh else "static"
        raise RuntimeError("no " + kind + " mesh for snapshot part: " + ", ".join(missing))
    return found


def _part_meshes():
    # A multi-part import names each part after its mesh datablock, because the parts keep their
    # own pivots. So the parts are found by those names in dest. A datablock UE did not create is
    # left out, and _resolve_expected reports its part.
    dest = PARAMS["dest"]
    parts = []
    for datablock in sorted(PARAMS["mesh_names"]):
        path = dest + "/" + _asset_name(datablock)
        if unreal.EditorAssetLibrary.does_asset_exist(path):
            mesh = _load(path)
            if isinstance(mesh, unreal.StaticMesh):
                parts.append((path, mesh))
    return parts


def _ensure_rig_assets(mesh):
    # The Desktop rig must hold its skeleton and physics asset in dest. The skeleton has to come
    # from the import. The physics asset is created when the import did not make it (#141).
    skeleton = _skeleton_path()
    if not unreal.EditorAssetLibrary.does_asset_exist(skeleton):
        raise RuntimeError("skeleton missing after import: " + skeleton)
    physics = _physics_path()
    if unreal.EditorAssetLibrary.does_asset_exist(physics):
        return
    subsystem = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    created = subsystem.create_physics_asset(mesh)
    if created is None:
        raise RuntimeError("create_physics_asset made no physics asset: " + physics)
    created_path = created.get_path_name().split(".")[0]
    if created_path != physics:
        unreal.EditorAssetLibrary.rename_asset(created_path, physics)
    if not unreal.EditorAssetLibrary.does_asset_exist(physics):
        raise RuntimeError("physics asset missing after import: " + physics)
    physics_asset = _load(physics)
    mesh.set_editor_property("physics_asset", physics_asset)
    unreal.EditorAssetLibrary.save_loaded_asset(physics_asset)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)


def _import_meshes(tools):
    fbx = os.path.join(PARAMS["variant_dir"], "SM_" + PARAMS["name"] + ".fbx")
    if not os.path.isfile(fbx):
        raise RuntimeError("FBX missing from the variant folder: " + fbx)
    if PARAMS["rigged"]:
        return _import_skeletal(tools, fbx)
    _import_fbx(tools, fbx, _static_options())
    if PARAMS["multi_part"]:
        # Scale and rename first, so the expected names below are the final names (#145, #141).
        parts = _part_meshes()
        _set_build_scale(parts)
        _rename_to_parts(parts)
    return _resolve_expected(unreal.StaticMesh)


def _import_skeletal(tools, fbx):
    desktop = PARAMS["variant"] == "desktop"
    _import_fbx(tools, fbx, _skeletal_options(desktop))
    meshes = _resolve_expected(unreal.SkeletalMesh)
    if len(meshes) != 1:
        raise RuntimeError("the FBX imported " + str(len(meshes)) + " skeletal meshes: " + fbx)
    object_path, mesh = meshes[0]
    if desktop:
        _ensure_rig_assets(mesh)
    lod_count = 1
    if not desktop:
        subsystem = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
        for level in (1, 2):
            lod_fbx = os.path.join(
                PARAMS["variant_dir"], "SM_" + PARAMS["name"] + "_LOD" + str(level) + ".fbx"
            )
            if not os.path.isfile(lod_fbx):
                continue
            placed = subsystem.import_lod(mesh, level, lod_fbx)
            if placed != level:
                raise RuntimeError(
                    lod_fbx + " was imported as LOD " + str(placed) + ", expected " + str(level)
                )
            lod_count += 1
    LOD_COUNT[object_path] = lod_count
    return meshes


def _asset_name(text):
    # UE replaces every character outside [A-Za-z0-9_] in an asset name with an underscore.
    return "".join(char if char in ASSET_NAME_CHARS else "_" for char in text)


def _set_build_scale(meshes):
    # Written on every run, not only while the scale is 1.0: the write is absolute, so it never
    # compounds, and it rebuilds the mesh, so the bounds are those of the new geometry even when
    # an earlier import left the mesh at scale 100.
    subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    for _, mesh in meshes:
        for lod in range(mesh.get_num_lods()):
            settings = subsystem.get_lod_build_settings(mesh, lod)
            settings.build_scale3d = unreal.Vector(CM_PER_METER, CM_PER_METER, CM_PER_METER)
            subsystem.set_lod_build_settings(mesh, lod, settings)
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)


def _rename_to_parts(meshes):
    dest = PARAMS["dest"]
    export_names = {
        _asset_name(datablock): export for datablock, export in PARAMS["mesh_names"].items()
    }
    for object_path, mesh in meshes:
        asset_name = object_path.rsplit("/", 1)[-1]
        export = export_names.get(asset_name)
        if export is None or export == asset_name:
            continue
        target = dest + "/" + export
        if unreal.EditorAssetLibrary.does_asset_exist(target):
            unreal.EditorAssetLibrary.consolidate_assets(mesh, [_load(target)])
        unreal.EditorAssetLibrary.rename_asset(object_path, target)


def _bounds(mesh):
    box = mesh.get_bounding_box()
    return {
        "min": [box.min.x, box.min.y, box.min.z],
        "max": [box.max.x, box.max.y, box.max.z],
    }


def _skeletal_bounds(mesh):
    bounds = mesh.get_bounds()
    origin = bounds.origin
    extent = bounds.box_extent
    return {
        "min": [origin.x - extent.x, origin.y - extent.y, origin.z - extent.z],
        "max": [origin.x + extent.x, origin.y + extent.y, origin.z + extent.z],
    }


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
        skeletal = isinstance(mesh, unreal.SkeletalMesh)
        if skeletal:
            RESULT["skeletal_meshes"][mesh_name] = {
                "path": object_path,
                "bounds": _skeletal_bounds(mesh),
                "lod_count": LOD_COUNT[object_path],
                "skeleton": _skeleton_path(),
                "physics_asset": _physics_path(),
            }
            slots = mesh.get_editor_property("materials")
        else:
            RESULT["static_meshes"][mesh_name] = {
                "path": object_path,
                "bounds": _bounds(mesh),
                "lod_count": mesh.get_num_lods(),
            }
            slots = mesh.static_materials
        for index, slot in enumerate(slots):
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
            if skeletal:
                slot.material_interface = instance
                slots[index] = slot
            else:
                mesh.set_material(index, instance)
            RESULT["materials"][slot_name] = dest + "/MI_" + name + "_" + part
        if skeletal:
            mesh.set_editor_property("materials", slots)
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)


def _run():
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    _import_textures(tools)
    meshes = _import_meshes(tools)
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

    def execute_python_code(self, code: str, *, timeout: float | None = None) -> str:
        """Run UE Python in the editor and return the tool's text output."""
        ...


def build_import_code(
    variant_dir: str,
    dest: str,
    name: str,
    report: dict[str, Any],
    skeleton_dest: str | None = None,
) -> str:
    """Return the UE Python that imports one variant folder into ``dest``.

    ``report`` is the pre-export contract report. Its snapshot tells the UE side which
    ``MESH`` parts of this variant must come back as meshes, so a missing part fails before any
    material is bound, and whether the asset is rigged (it holds the armature ``SK_<Name>``).
    A rigged Mobile variant reads its skeleton and physics asset from ``skeleton_dest``, the
    Desktop folder, so ``skeleton_dest`` is required for it.
    """
    variant = _variant_of(dest)
    rigged = _is_rigged(report, name)
    if rigged and variant == "mobile" and skeleton_dest is None:
        raise ValueError("a rigged Mobile import needs skeleton_dest, the Desktop folder")
    params: dict[str, Any] = {
        "variant": variant,
        "variant_dir": variant_dir,
        "dest": dest,
        "name": name,
        "rigged": rigged,
        "skeleton_dest": skeleton_dest if skeleton_dest is not None else dest,
        "expected_meshes": _expected_mesh_candidates(report, variant, rigged),
        "multi_part": _multi_part(report, variant, rigged),
        "mesh_names": _mesh_names(report, variant, rigged),
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

    Static and skeletal meshes are both measured. A rigged asset's LOD1 and LOD2 entries are
    skipped, and so are a static LOD group's (#146). Raises ``import_ue.pivot_mismatch`` on any
    mismatch, on a part with no mesh, or on a snapshot part that has no ``local_bounds``.
    """
    variant = str(result.get("variant", ""))
    snapshot = report.get("snapshot")
    static = result.get("static_meshes")
    skeletal = result.get("skeletal_meshes", {})
    if (
        not isinstance(snapshot, dict)
        or not isinstance(static, dict)
        or not isinstance(skeletal, dict)
    ):
        _fail_pivot("the report or the UE result has no snapshot or static_meshes")
    measured: dict[str, Any] = {**static, **skeletal}
    rigged = _is_rigged(report, str(result.get("name", "")))
    groups = _lod_groups(report, variant, rigged)
    for key in sorted(snapshot):
        entry = snapshot[key]
        if not isinstance(entry, dict) or entry.get("type") != "MESH":
            continue
        if entry.get("variant") != variant:
            continue
        if _skipped_lod(key, rigged, groups):
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


def check_lod_counts(report: dict[str, Any], result: dict[str, Any]) -> None:
    """Check that each static LOD group imported as one Static Mesh with its snapshot's LOD count.

    A static LOD group is a non-rigged variant whose snapshot holds ``<base>_LOD0`` and its LOD
    objects (#146). UE builds one Static Mesh for it, matched here by the LOD0 key. Its
    ``lod_count`` must equal the number of LOD objects. Raises ``import_ue.failed``, naming the mesh
    and both counts, when the count differs or is missing. A variant with no static LOD group,
    including every rigged asset, passes without a check.
    """
    variant = str(result.get("variant", ""))
    rigged = _is_rigged(report, str(result.get("name", "")))
    static = result.get("static_meshes")
    measured: dict[str, Any] = static if isinstance(static, dict) else {}
    for base, keys in _lod_groups(report, variant, rigged).items():
        found = _matching_mesh(f"{base}{_LOD0_SUFFIX}", measured)
        entry = measured[found] if found is not None else None
        actual = entry.get("lod_count") if isinstance(entry, dict) else None
        if isinstance(actual, int) and not isinstance(actual, bool) and actual == len(keys):
            continue
        mesh_name = found if found is not None else _export_name(base)
        shown = "missing" if actual is None else str(actual)
        _fail_import(
            f"{mesh_name} has {shown} LODs in Unreal; the snapshot has {len(keys)} LOD objects "
            f"({keys[0]}..{keys[-1]})"
        )


def import_variant(
    client: UnrealPythonClient,
    *,
    variant_dir: str,
    dest: str,
    name: str,
    report: dict[str, Any],
    skeleton_dest: str | None = None,
    retry: RetrySettings | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Import one variant through ``client``, then check its pivots. Return the UE result.

    A timed-out request is retried with back-off (#149, FR6).  The result records ``attempts``.
    The pivot check runs once, on the reply that succeeded.
    """
    code = build_import_code(variant_dir, dest, name, report, skeleton_dest=skeleton_dest)
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
    if result.get("ok") is not True:
        error_text = result.get("error") or "UE reported no error text"
        raise PipelineError(
            code="import_ue.failed",
            message=f"UE import of {dest} failed: {error_text}",
            remediation=_IMPORT_REMEDIATION,
            stage=_STAGE,
        )
    result["attempts"] = attempts
    check_lod_counts(report, result)
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


def _is_rigged(report: dict[str, Any], name: str) -> bool:
    """True when the report snapshot holds the armature SK_<Name>, which marks a rigged asset."""
    snapshot = report.get("snapshot")
    if not isinstance(snapshot, dict):
        return False
    entry = snapshot.get(f"SK_{name}")
    return isinstance(entry, dict) and entry.get("type") == "ARMATURE"


def _snapshot_meshes(report: dict[str, Any], variant: str) -> list[tuple[str, Any]]:
    """Every snapshot ``MESH`` entry of one variant, sorted by key, with no skipping."""
    snapshot = report.get("snapshot")
    if not isinstance(snapshot, dict):
        return []
    meshes: list[tuple[str, Any]] = []
    for key in sorted(snapshot):
        entry = snapshot[key]
        if (
            isinstance(entry, dict)
            and entry.get("type") == "MESH"
            and entry.get("variant") == variant
        ):
            meshes.append((key, entry))
    return meshes


def _lod_groups(report: dict[str, Any], variant: str, rigged: bool) -> dict[str, list[str]]:
    """Each static LOD group's base, mapped to its LOD object keys, LOD0 first (#146).

    A base is a group when its snapshot holds ``<base>_LOD0``. A rigged asset has no static LOD
    group, so it gets none.
    """
    if rigged:
        return {}
    levels: dict[str, list[tuple[int, str]]] = {}
    for key, _ in _snapshot_meshes(report, variant):
        match = _LOD_ANY.search(key)
        if match is not None:
            levels.setdefault(key[: match.start()], []).append((int(match.group(1)), key))
    return {
        base: [key for _, key in sorted(members)]
        for base, members in levels.items()
        if any(level == 0 for level, _ in members)
    }


def _skipped_lod(key: str, rigged: bool, groups: dict[str, list[str]]) -> bool:
    """True for a LOD1 or LOD2 object that UE gives no mesh of its own.

    A rigged asset's LODs are LODs of its Skeletal Mesh. A static LOD group's are LODs of its
    Static Mesh, so neither gets a mesh of its own.
    """
    if _LOD_EXTRA.search(key) is None:
        return False
    return rigged or _LOD_ANY.sub("", key) in groups


def _variant_meshes(report: dict[str, Any], variant: str, rigged: bool) -> list[tuple[str, Any]]:
    """The snapshot ``MESH`` entries of one variant that UE gives a mesh each, sorted by key."""
    groups = _lod_groups(report, variant, rigged)
    return [
        (key, entry)
        for key, entry in _snapshot_meshes(report, variant)
        if not _skipped_lod(key, rigged, groups)
    ]


def _expected_mesh_candidates(
    report: dict[str, Any], variant: str, rigged: bool
) -> list[list[str]]:
    return [
        sorted(_mesh_name_candidates(key)) for key, _ in _variant_meshes(report, variant, rigged)
    ]


def _multi_part(report: dict[str, Any], variant: str, rigged: bool) -> bool:
    """True when the variant has more than one base part, so its parts need their own pivots.

    Counts export names with any ``_LOD<n>`` suffix removed, as ghost1's ``_multi_part`` does.
    """
    bases = {
        _LOD_ANY.sub("", _export_name(key)) for key, _ in _variant_meshes(report, variant, rigged)
    }
    return len(bases) > 1


def _mesh_names(report: dict[str, Any], variant: str, rigged: bool) -> dict[str, str]:
    """Map each part's mesh datablock to its export name for this variant.

    A datablock shared by several parts is left out: UE names the mesh after that datablock, so
    no single export name can be given to it. Snapshot entries from before #145 have no ``mesh``
    key and are left out too.
    """
    parts = [
        (entry.get("mesh"), _export_name(key))
        for key, entry in _variant_meshes(report, variant, rigged)
        if isinstance(entry.get("mesh"), str)
    ]
    counts = Counter(datablock for datablock, _ in parts)
    return {datablock: export for datablock, export in parts if counts[datablock] == 1}


def _mesh_name_candidates(key: str) -> list[str]:
    """The names a snapshot key may carry in UE, in match order, without duplicates.

    The key, then its export name. A ``_LOD0`` key also gives both without ``_LOD0``, because UE
    names a static LOD group after its Empty, ``SM_<Name>``, and not after LOD0 (#146).
    """
    export = _export_name(key)
    names = [key, export]
    if key.endswith(_LOD0_SUFFIX):
        names += [key[: -len(_LOD0_SUFFIX)], export[: -len(_LOD0_SUFFIX)]]
    return list(dict.fromkeys(names))


def _matching_mesh(key: str, measured: dict[str, Any]) -> str | None:
    for candidate in _mesh_name_candidates(key):
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
    "check_lod_counts",
    "check_pivots",
    "import_variant",
    "parse_nmg_result",
]
