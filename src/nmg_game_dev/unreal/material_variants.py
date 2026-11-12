"""List an asset's material variants from Unreal, from the tags finalize writes (#148).

list_material_variants runs UE Python through the same client the import uses. The UE code reads
nmg.asset, nmg.material_variant, and nmg.material_slot on each material instance in the Desktop and
Mobile folders, so the names come from the tags and never from parsing asset names.
"""

from __future__ import annotations

import json
from typing import Any, Final

from nmg_game_dev.pipeline.errors import PipelineError

from .import_asset import UnrealPythonClient, parse_nmg_result

_STAGE: Final = "finalize"
_VARIANT_FOLDERS: Final = ("desktop", "mobile")

_LIST_TEMPLATE: Final = r"""
import json
import unreal

PARAMS = json.loads(__PARAMS__)
RESULT = {"ok": False, "instances": [], "error": None}


def _tag(asset, key):
    return str(unreal.EditorAssetLibrary.get_metadata_tag(asset, key) or "")


def _run():
    for folder_key, folder in sorted(PARAMS["folders"].items()):
        if not unreal.EditorAssetLibrary.does_directory_exist(folder):
            continue
        for asset_path in unreal.EditorAssetLibrary.list_assets(
            folder, recursive=False, include_folder=False
        ):
            path = str(asset_path).split(".")[0]
            asset = unreal.EditorAssetLibrary.load_asset(path)
            if asset is None or not isinstance(asset, unreal.MaterialInstanceConstant):
                continue
            if _tag(asset, "nmg.asset") != PARAMS["name"]:
                continue
            RESULT["instances"].append(
                {
                    "folder": folder_key,
                    "path": path,
                    "variant": _tag(asset, "nmg.material_variant"),
                    "material": _tag(asset, "nmg.material_slot"),
                }
            )
    RESULT["ok"] = True


try:
    _run()
except Exception as error:
    RESULT["error"] = type(error).__name__ + ": " + str(error)
print("NMG_RESULT " + json.dumps(RESULT, sort_keys=True))
"""


def build_list_code(name: str, folders: dict[str, str]) -> str:
    """Return the UE Python that reads the material-variant tags in each folder of ``folders``."""
    params = {"name": name, "folders": folders}
    return _LIST_TEMPLATE.replace("__PARAMS__", json.dumps(json.dumps(params, sort_keys=True)))


def list_material_variants(
    client: UnrealPythonClient,
    category: str,
    name: str,
) -> list[dict[str, Any]]:
    """Return the material variants of <name> in <category>, sorted by material, then name.

    Each row is {"name", "material", "desktop", "mobile"}, where the last two are the variant's
    material instance path in each folder, or None. An asset with no tagged variants, or one whose
    folders are missing, returns []. An unreachable Unreal MCP raises mcp.unreal.unreachable.
    """
    folders = {
        variant: f"/Game/{category}/{name}/{variant.capitalize()}" for variant in _VARIANT_FOLDERS
    }
    result = parse_nmg_result(client.execute_python_code(build_list_code(name, folders)))
    if result.get("ok") is not True:
        raise PipelineError(
            code="finalize.material_variants_failed",
            message=f"UE could not list the material variants of {name}: "
            f"{result.get('error') or 'UE reported no error text'}",
            remediation="Read the UE error in the message, confirm the editor is idle and the "
            "asset is in Content, then rerun.",
            stage=_STAGE,
        )
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for item in result.get("instances") or []:
        if not isinstance(item, dict):
            continue
        folder = item.get("folder")
        variant = str(item.get("variant") or "")
        material = str(item.get("material") or "")
        if folder not in folders or not variant or not material:
            continue
        row = rows.setdefault(
            (material, variant),
            {"name": variant, "material": material, "desktop": None, "mobile": None},
        )
        row[str(folder)] = str(item.get("path") or "")
    return [rows[key] for key in sorted(rows)]
