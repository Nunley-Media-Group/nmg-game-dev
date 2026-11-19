"""``import_audio``: validate, store under SourceArt, and import into Godot (#155, #249 FR5).

The CLI and the finalize MCP tool both call this function, so they return the same result. Every
prerequisite is checked before the first write: the request, a free ``SourceArt`` target, the
Godot project at ``game/``, a free ``game/assets/Audio/`` target, and (for music) ffmpeg.
A missing Godot binary (``godot.not_found``) is not fatal: the files are still written for Godot's
next import, and the result carries ``imported_to_godot: false`` and a ``warning``. Any other
import error leaves the stored WAV in place and propagates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from nmg_game_dev.audio import godot_import, paths
from nmg_game_dev.audio.convert import store_wav
from nmg_game_dev.audio.errors import AudioError
from nmg_game_dev.audio.ffmpeg import FfmpegRunner, SubprocessFfmpegRunner, resolve_ffmpeg
from nmg_game_dev.audio.request import AudioRequest
from nmg_game_dev.godot.binary import resolve_godot
from nmg_game_dev.godot.runner import GodotRunner, SubprocessGodotRunner
from nmg_game_dev.pipeline.errors import PipelineError

GODOT_NOT_FOUND: Final = "godot.not_found"


def import_audio(
    file: str | Path,
    name: str,
    kind: str,
    loop: bool = False,
    *,
    project_root: Path | None = None,
    godot: GodotRunner | None = None,
    ffmpeg: FfmpegRunner | None = None,
) -> dict[str, Any]:
    """Store ``file`` as ``SourceArt/Audio/<SFX|Music>/<name>.wav`` and import it into Godot.

    A sound effect becomes an ``AudioStreamWAV`` at ``res://assets/Audio/<name>.wav``; music is
    encoded with ffmpeg and becomes an ``AudioStreamOggVorbis`` at ``res://assets/Audio/<name>.ogg``.
    ``godot`` defaults to the binary ``resolve_godot`` finds and ``ffmpeg`` to the one
    ``resolve_ffmpeg`` finds. Raises ``AudioError`` before any write when the request is invalid,
    a target already exists, ``game/project.godot`` is missing, or music has no ffmpeg.
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
    godot_import.check_target(root, request.kind, request.name)
    encoder = ffmpeg
    if request.kind == "music" and encoder is None:
        encoder = SubprocessFfmpegRunner(resolve_ffmpeg())
    runner, warning = _godot_runner(godot)

    stored = store_wav(request.file, target)
    if request.kind == "sfx":
        imported = godot_import.import_wav(root, target, request.name, request.loop, runner)
    else:
        imported = godot_import.import_ogg(
            root, target, request.name, request.loop, runner, encoder
        )
    result: dict[str, Any] = {
        "kind": request.kind,
        "name": request.name,
        "source_art": str(target),
        "godot_asset": imported["godot_asset"],
        **stored,
        "looping": request.loop,
        "imported_to_godot": imported["imported_to_godot"],
    }
    if warning is not None:
        result["warning"] = warning
    return result


def _godot_runner(
    godot: GodotRunner | None,
) -> tuple[GodotRunner | None, dict[str, str] | None]:
    """Return the runner to import with, or ``None`` and a warning when Godot is not installed."""
    if godot is not None:
        return godot, None
    try:
        return SubprocessGodotRunner(resolve_godot()), None
    except PipelineError as error:
        if error.code != GODOT_NOT_FOUND:
            raise
        return None, {
            "code": error.code,
            "message": f"{error.message} The files were written; Godot imports them the next "
            "time it opens the project.",
            "remediation": error.remediation,
        }
