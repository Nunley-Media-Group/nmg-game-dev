"""Import one stored WAV into Unreal as a SoundWave through the Unreal MCP (#155 FR4).

``build_audio_import_code`` returns UE Python that imports the WAV as ``SW_<Name>``, sets
``looping``, saves the asset, and prints one ``NMG_RESULT {json}`` line, even on failure.
``run_import`` runs that code through an ``UnrealPythonClient`` and parses the line. A missing
editor (``mcp.unreal.unreachable``) passes through unchanged, so the caller can turn it into a
warning. Every other failure becomes ``audio.import_failed``.
"""

from __future__ import annotations

import json
from typing import Any, Final

from nmg_game_dev.audio.errors import AudioError
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.unreal import UnrealPythonClient, parse_nmg_result

UNREACHABLE_CODE: Final = "mcp.unreal.unreachable"

_IMPORT_REMEDIATION: Final = (
    "Read the UE error in the message. Confirm the editor is idle and that no asset already "
    "exists at the SoundWave path, then import the sound again. The stored WAV is kept."
)

_IMPORT_TEMPLATE: Final = r"""
import json
import unreal

PARAMS = json.loads(__PARAMS__)
RESULT = {
    "ok": False,
    "asset": PARAMS["asset"],
    "looping": PARAMS["loop"],
    "error": None,
}


def _import():
    asset_path = PARAMS["asset"]
    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        raise RuntimeError("an asset already exists at " + asset_path)
    task = unreal.AssetImportTask()
    task.filename = PARAMS["wav"]
    task.destination_path = PARAMS["dest_folder"]
    task.destination_name = PARAMS["asset_name"]
    task.automated = True
    task.replace_existing = False
    task.save = True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    sound = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not isinstance(sound, unreal.SoundWave):
        raise RuntimeError("the import created no SoundWave at " + asset_path)
    sound.set_editor_property("looping", PARAMS["loop"])
    unreal.EditorAssetLibrary.save_loaded_asset(sound)
    RESULT["ok"] = True


try:
    _import()
except Exception as error:
    RESULT["error"] = type(error).__name__ + ": " + str(error)
print("NMG_RESULT " + json.dumps(RESULT, sort_keys=True))
"""


def build_audio_import_code(wav: str, dest_folder: str, asset_name: str, loop: bool) -> str:
    """Return the UE Python that imports ``wav`` as ``<dest_folder>/<asset_name>``."""
    params: dict[str, Any] = {
        "wav": wav,
        "dest_folder": dest_folder,
        "asset_name": asset_name,
        "asset": f"{dest_folder}/{asset_name}",
        "loop": bool(loop),
    }
    return _IMPORT_TEMPLATE.replace("__PARAMS__", json.dumps(json.dumps(params, sort_keys=True)))


def run_import(
    client: UnrealPythonClient,
    *,
    wav: str,
    dest_folder: str,
    asset_name: str,
    loop: bool,
) -> dict[str, Any]:
    """Import the WAV through ``client`` and return the UE result. Raise on any import failure."""
    code = build_audio_import_code(wav, dest_folder, asset_name, loop)
    asset = f"{dest_folder}/{asset_name}"
    try:
        output = client.execute_python_code(code)
    except PipelineError as error:
        if error.code == UNREACHABLE_CODE:
            raise
        raise _import_failed(asset, error.message) from error
    try:
        result = parse_nmg_result(output)
    except PipelineError as error:
        raise _import_failed(asset, error.message) from error
    if result.get("ok") is not True:
        reason = result.get("error") or "UE reported no error text"
        raise _import_failed(asset, str(reason))
    return result


def _import_failed(asset: str, reason: str) -> AudioError:
    return AudioError(
        code="audio.import_failed",
        message=f"UE import of {asset} failed: {reason}",
        remediation=_IMPORT_REMEDIATION,
    )
