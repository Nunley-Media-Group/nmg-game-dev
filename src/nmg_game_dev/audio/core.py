"""``import_audio``: validate, store under SourceArt, and import into Unreal (#155 FR1, FR2).

The CLI and the finalize MCP tool both call this function, so they return the same result. A
``PipelineError`` with the ``mcp.unreal.unreachable`` code is not fatal: the WAV stays under
``SourceArt/Audio/`` and the result carries a ``warning``. An ``audio.import_failed`` error leaves
the WAV in place and propagates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nmg_game_dev.audio import paths
from nmg_game_dev.audio.convert import store_wav
from nmg_game_dev.audio.errors import AudioError
from nmg_game_dev.audio.request import AudioRequest
from nmg_game_dev.audio.unreal_import import UNREACHABLE_CODE, run_import
from nmg_game_dev.pipeline.clients.unreal_mcp import UnrealMcpClient
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.unreal import UnrealPythonClient


def import_audio(
    file: str | Path,
    name: str,
    kind: str,
    loop: bool = False,
    *,
    project_root: Path | None = None,
    unreal_client: UnrealPythonClient | None = None,
) -> dict[str, Any]:
    """Store ``file`` as ``SourceArt/Audio/<SFX|Music>/<name>.wav`` and import it as a SoundWave.

    Raises ``AudioError`` before any write when the request is invalid, and when the target WAV
    already exists. ``unreal_client`` defaults to ``UnrealMcpClient()``, which reads
    ``UE_MCP_PORT``.
    """
    request = AudioRequest(file=Path(file), name=name, kind=kind, loop=bool(loop))
    request.validate()
    root = project_root if project_root is not None else paths.project_root()
    target = paths.source_art(root, request.kind, request.name)
    if target.exists():
        raise AudioError(
            code="audio.asset_exists",
            message=f"{target} already exists",
            remediation="Choose another name, or delete the existing WAV if you mean to replace "
            "it. Overwriting an imported sound in place is not supported.",
        )

    stored = store_wav(request.file, target)
    result: dict[str, Any] = {
        "kind": request.kind,
        "name": request.name,
        "source_art": str(target),
        "unreal_asset": paths.unreal_asset(request.kind, request.name),
        **stored,
        "looping": request.loop,
    }

    client = unreal_client if unreal_client is not None else UnrealMcpClient()
    try:
        run_import(
            client,
            wav=str(target),
            dest_folder=paths.unreal_folder(request.kind),
            asset_name=paths.asset_name(request.name),
            loop=request.loop,
        )
    except PipelineError as error:
        if error.code != UNREACHABLE_CODE:
            raise
        result["imported_to_unreal"] = False
        result["warning"] = {
            "code": error.code,
            "message": error.message,
            "remediation": error.remediation,
        }
    else:
        result["imported_to_unreal"] = True
    return result
