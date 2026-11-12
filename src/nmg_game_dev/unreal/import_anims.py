"""UE Python for the finalize ``import_anims`` step: clip AnimSequences on the Desktop skeleton.

``build_anim_import_code`` returns one UE Python program. It runs through the same Unreal MCP client
as the mesh import, and it prints exactly one ``NMG_RESULT {json}`` line, even on failure. The host
reads that result with ``pipeline/anims.py``. Nothing here runs outside the editor. Tests check the
generated text and the host's handling of a reply.

The program runs in this order, and it changes nothing until every check has passed:

1. The character's own Desktop skeleton must exist. Otherwise it reports ``skeleton_not_found``.
2. Every ``compatible_with`` target skeleton must exist and have the same reference bone names.
   Otherwise it reports ``skeleton_not_found`` or ``skeleton_mismatch`` with the differing bones.
3. Each clip that missed the cache is imported as an AnimSequence named ``A_<Name>_<Clip>`` in the
   Animations folder, on the Desktop skeleton. A clip whose AnimSequence is gone is imported again.
   Any imported object that is not an AnimSequence fails the step.
4. Every clip's AnimSequence is measured: its skeleton path and its sampled key count.
5. Sequences named ``A_<Name>_*`` that are no longer clips are listed under ``stale``. They are
   never deleted.
6. Only when the measured values match the sidecar, and no earlier check failed, the compatible
   skeletons are registered in both directions. Each list gains a path at most once.

Measured values go back to the host, which raises ``import_anims.clip_mismatch`` for any clip whose
values differ from the sidecar.

The UE calls used here follow the editor's Python API as it is used for the mesh import in
``import_asset.py``. The reference-bone and compatible-skeleton reads are the least certain part.
They fail closed: when a value cannot be read, the step reports an error and registers nothing.
"""

from __future__ import annotations

import json
from typing import Any, Final

_ANIM_TEMPLATE: Final = r"""
import json
import unreal

PARAMS = json.loads(__PARAMS__)
RESULT = {
    "ok": False,
    "skeleton": PARAMS["skeleton"],
    "blocked": None,
    "clips": {},
    "mismatch": [],
    "stale": [],
    "compatible": [],
    "error": None,
}


def _load(path):
    return unreal.EditorAssetLibrary.load_asset(path)


def _object_path(obj):
    return str(obj.get_path_name()).split(".")[0]


def _bone_names(skeleton):
    try:
        return [str(name) for name in skeleton.get_bone_names()]
    except AttributeError:
        reference = skeleton.get_editor_property("reference_skeleton")
        infos = reference.get_editor_property("ref_bone_info")
        return [str(info.get_editor_property("name")) for info in infos]


def _sampled_keys(sequence):
    for method in ("get_number_of_sampled_keys", "get_number_of_frames", "get_num_frames"):
        reader = getattr(sequence, method, None)
        if reader is not None:
            return int(reader())
    raise RuntimeError("cannot read the sampled key count of " + sequence.get_name())


def _compatible_paths(skeleton):
    items = skeleton.get_editor_property("compatible_skeletons")
    return [str(item).split(".")[0] for item in items]


def _add_compatible(skeleton, other_path):
    current = list(skeleton.get_editor_property("compatible_skeletons"))
    if other_path not in _compatible_paths(skeleton):
        current.append(unreal.SoftObjectPath(other_path))
        skeleton.set_editor_property("compatible_skeletons", current)
        return True
    return False


def _check_targets(own_names):
    for target in PARAMS["compatible"]:
        skeleton = _load(target["skeleton"])
        if skeleton is None:
            RESULT["blocked"] = {"code": "skeleton_not_found", "target": target["name"],
                                 "path": target["skeleton"], "bones": []}
            return False
        names = _bone_names(skeleton)
        if names != own_names:
            differing = sorted(set(names) ^ set(own_names)) or ["bone order differs"]
            RESULT["blocked"] = {"code": "skeleton_mismatch", "target": target["name"],
                                 "path": target["skeleton"], "bones": differing}
            return False
    return True


def _import_clip(tools, clip):
    options = unreal.FbxImportUI()
    options.set_editor_property("import_mesh", False)
    options.set_editor_property("import_as_skeletal", True)
    options.set_editor_property("import_animations", True)
    options.set_editor_property("import_materials", False)
    options.set_editor_property("import_textures", False)
    options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_ANIMATION)
    options.set_editor_property("skeleton", _load(PARAMS["skeleton"]))
    task = unreal.AssetImportTask()
    task.filename = clip["file"]
    task.destination_path = PARAMS["anim_dir"]
    task.destination_name = clip["asset_name"]
    task.replace_existing = True
    task.automated = True
    task.save = True
    task.options = options
    tools.import_asset_tasks([task])
    extra = []
    for path in list(task.imported_object_paths):
        if not isinstance(_load(str(path).split(".")[0]), unreal.AnimSequence):
            extra.append(str(path))
    if extra:
        raise RuntimeError(
            "import of " + clip["name"] + " created non-AnimSequence assets: " + ", ".join(extra)
        )


def _run():
    own = _load(PARAMS["skeleton"])
    if own is None:
        RESULT["blocked"] = {"code": "skeleton_not_found", "target": PARAMS["skeleton"],
                             "path": PARAMS["skeleton"], "bones": []}
        return
    own_names = _bone_names(own)
    if not _check_targets(own_names):
        return
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    for clip in PARAMS["clips"]:
        present = _load(clip["asset_path"]) is not None
        if clip["import"] or not present:
            _import_clip(tools, clip)
            imported = True
        else:
            imported = False
        sequence = _load(clip["asset_path"])
        measured = {
            "asset_path": clip["asset_path"],
            "skeleton": _object_path(sequence.get_editor_property("skeleton")),
            "frame_count": _sampled_keys(sequence),
            "imported": imported,
        }
        RESULT["clips"][clip["name"]] = measured
        if measured["skeleton"] != PARAMS["skeleton"]:
            RESULT["mismatch"].append({"clip": clip["name"], "field": "skeleton",
                                       "expected": PARAMS["skeleton"],
                                       "measured": measured["skeleton"]})
        if measured["frame_count"] != clip["expected_frame_count"]:
            RESULT["mismatch"].append({"clip": clip["name"], "field": "frame_count",
                                       "expected": clip["expected_frame_count"],
                                       "measured": measured["frame_count"]})
    current = {clip["asset_name"] for clip in PARAMS["clips"]}
    for path in unreal.EditorAssetLibrary.list_assets(PARAMS["anim_dir"], recursive=False,
                                                      include_folder=False):
        name = str(path).split(".")[0].rsplit("/", 1)[-1]
        if name.startswith(PARAMS["prefix"]) and name not in current:
            RESULT["stale"].append(PARAMS["anim_dir"] + "/" + name)
    if RESULT["mismatch"]:
        return
    for target in PARAMS["compatible"]:
        other = _load(target["skeleton"])
        _add_compatible(own, target["skeleton"])
        _add_compatible(other, PARAMS["skeleton"])
        unreal.EditorAssetLibrary.save_loaded_asset(other)
        RESULT["compatible"].append(target["skeleton"])
    if PARAMS["compatible"]:
        unreal.EditorAssetLibrary.save_loaded_asset(own)
    RESULT["ok"] = True


try:
    _run()
except Exception as error:
    RESULT["error"] = type(error).__name__ + ": " + str(error)
print("NMG_RESULT " + json.dumps(RESULT, sort_keys=True))
"""


def build_anim_import_code(params: dict[str, Any]) -> str:
    """Return the UE Python that imports, verifies, and registers the clips described by ``params``.

    ``params`` holds ``name``, ``anim_dir``, ``skeleton``, ``prefix`` (``A_<Name>_``), ``clips``
    (each with ``name``, ``asset_name``, ``asset_path``, ``file``, ``import``, and
    ``expected_frame_count``), and ``compatible`` (each with ``name`` and ``skeleton``).
    """
    return _ANIM_TEMPLATE.replace("__PARAMS__", json.dumps(json.dumps(params, sort_keys=True)))


__all__ = ["build_anim_import_code"]
