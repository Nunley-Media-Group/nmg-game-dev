"""``import_audio`` and ``refinish``: finish, store under SourceArt, import into Godot
(#155, #252).

The CLI and the finalize MCP tool both call these functions, so they return the same result. Every
prerequisite is checked before the first write: the request, the finishing settings in
``audio.json``, a free ``SourceArt`` target (or a byte-identical one, which re-finishes), the Godot
project at ``game/``, a free ``game/assets/Audio/`` target, and (for music) ffmpeg.

Finishing (#252) runs on the stored WAV into a scratch folder, and the game copy is the finished
file. ``SourceArt`` keeps the input bytes. ``refinish`` runs the same finish and import again from
``SourceArt`` with each sound's stored settings.

A missing Godot binary (``godot.not_found``) is not fatal: the files are still written for Godot's
next import, and the result carries ``imported_to_godot: false`` and a ``warning``. Any other
import error leaves the stored WAV in place and propagates.
"""

from __future__ import annotations

import filecmp
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from nmg_game_dev.audio import godot_import, paths
from nmg_game_dev.audio import settings as sound_settings
from nmg_game_dev.audio.convert import store_wav
from nmg_game_dev.audio.errors import AudioError
from nmg_game_dev.audio.ffmpeg import FfmpegRunner, SubprocessFfmpegRunner, resolve_ffmpeg
from nmg_game_dev.audio.finish import finish_wav
from nmg_game_dev.audio.request import AudioRequest
from nmg_game_dev.audio.settings import FinishSettings, StoredSound
from nmg_game_dev.godot.binary import resolve_godot
from nmg_game_dev.godot.runner import GodotRunner, SubprocessGodotRunner
from nmg_game_dev.pipeline.errors import PipelineError

GODOT_NOT_FOUND: Final = "godot.not_found"
UNKNOWN_SOUND: Final = "audio.unknown_sound"


def import_audio(
    file: str | Path,
    name: str,
    kind: str,
    loop: bool = False,
    *,
    max_seconds: float | None = None,
    loudness_lufs: float | None = None,
    loop_crossfade_ms: int | None = None,
    finish: bool | None = None,
    project_root: Path | None = None,
    godot: GodotRunner | None = None,
    ffmpeg: FfmpegRunner | None = None,
) -> dict[str, Any]:
    """Finish ``file``, store it as ``SourceArt/Audio/<SFX|Music>/<name>.wav``, and import it.

    A sound effect becomes an ``AudioStreamWAV`` at ``res://assets/Audio/<name>.wav``; music is
    encoded with ffmpeg and becomes an ``AudioStreamOggVorbis`` at
    ``res://assets/Audio/<name>.ogg``.
    The four finishing arguments (``max_seconds``, ``loudness_lufs``, ``loop_crossfade_ms``,
    ``finish``) override the sound's stored settings; a value not passed comes from
    ``audio.json`` or the kind's default. ``godot`` defaults to the binary ``resolve_godot``
    finds and ``ffmpeg`` to the one ``resolve_ffmpeg`` finds. Raises ``AudioError`` before any
    write when the request or a setting is invalid, a different file (or a sound of the other
    kind) already holds the name, ``game/project.godot`` is missing, or music has no ffmpeg. A
    byte-identical file re-finishes the sound with the same settings.
    """
    request = AudioRequest(file=Path(file), name=name, kind=kind, loop=bool(loop))
    request.validate()
    root = project_root if project_root is not None else paths.project_root()
    settings = sound_settings.resolve(
        root,
        request.name,
        request.kind,
        finish=finish,
        max_seconds=max_seconds,
        loudness_lufs=loudness_lufs,
        loop_crossfade_ms=loop_crossfade_ms,
    )
    other_kind = "music" if request.kind == "sfx" else "sfx"
    other = paths.source_art(root, other_kind, request.name)
    if other.exists():
        raise AudioError(
            code="audio.asset_exists",
            message=f"{request.name} is already stored as {other_kind} at {other}",
            remediation="Choose another name. A name holds one sound, either a sound effect or "
            "music, so its settings in audio.json and refinish stay unambiguous.",
        )
    target = paths.source_art(root, request.kind, request.name)
    with tempfile.TemporaryDirectory(prefix="nmg-audio-") as scratch_name:
        scratch = Path(scratch_name)
        replace = target.exists()
        if replace:
            stored = store_wav(request.file, scratch / "probe.wav")
            if not filecmp.cmp(scratch / "probe.wav", target, shallow=False):
                raise _asset_exists(target)
        godot_import.check_target(root, request.kind, request.name, replace=replace)
        encoder = ffmpeg
        if request.kind == "music" and encoder is None:
            encoder = SubprocessFfmpegRunner(resolve_ffmpeg())
        runner, warning = _godot_runner(godot)

        if not replace:
            stored = store_wav(request.file, target)
        report, imported = _finish_and_import(
            root,
            request.kind,
            request.name,
            request.loop,
            target,
            settings,
            scratch,
            runner,
            encoder,
            replace=replace,
        )
        sound_settings.save(root, request.name, request.kind, request.loop, settings)
    result: dict[str, Any] = {
        "kind": request.kind,
        "name": request.name,
        "source_art": str(target),
        "godot_asset": imported["godot_asset"],
        **stored,
        "looping": request.loop,
        "imported_to_godot": imported["imported_to_godot"],
        "finish": report,
        "settings": sound_settings.describe(settings),
    }
    if warning is not None:
        result["warning"] = warning
    return result


def refinish(
    names: Sequence[str] | None = None,
    *,
    project_root: Path | None = None,
    godot: GodotRunner | None = None,
    ffmpeg: FfmpegRunner | None = None,
) -> list[dict[str, Any]]:
    """Re-finish stored sounds from ``SourceArt`` with their ``audio.json`` settings (#252 AC5).

    ``names=None`` re-finishes every entry in ``audio.json``; otherwise each named entry, in sorted
    name order. Raises ``audio.unknown_sound`` for a name with no entry or no stored WAV, and
    ``audio.settings_invalid`` for an unreadable ``audio.json``. Every check runs before the first
    write. Each game copy is replaced in place.
    """
    root = project_root if project_root is not None else paths.project_root()
    stored = sound_settings.load(root)
    if names is None:
        selected = sorted(stored)
    else:
        selected = sorted(set(names))
        for name in selected:
            if name not in stored:
                raise _unknown_sound(
                    f"{name} has no entry in {paths.settings_file(root)}",
                    "Pass a name that audio.json lists, or run refinish --all to re-finish every "
                    "sound it lists.",
                )
    sounds: list[tuple[str, StoredSound, Path]] = []
    for name in selected:
        sound = stored[name]
        source = paths.source_art(root, sound.kind, name)
        if not source.is_file():
            raise _unknown_sound(
                f"the stored WAV {source} is missing",
                "Import the sound again from its original file, which stores the WAV again.",
            )
        godot_import.check_target(root, sound.kind, name, replace=True)
        sounds.append((name, sound, source))

    encoder = ffmpeg
    if encoder is None and any(sound.kind == "music" for _, sound, _ in sounds):
        encoder = SubprocessFfmpegRunner(resolve_ffmpeg())
    runner, warning = _godot_runner(godot)

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="nmg-audio-") as scratch_name:
        for name, sound, source in sounds:
            report, imported = _finish_and_import(
                root,
                sound.kind,
                name,
                sound.loop,
                source,
                sound.settings,
                Path(scratch_name),
                runner,
                encoder,
                replace=True,
            )
            entry: dict[str, Any] = {
                "kind": sound.kind,
                "name": name,
                "source_art": str(source),
                "godot_asset": imported["godot_asset"],
                "looping": sound.loop,
                "imported_to_godot": imported["imported_to_godot"],
                "finish": report,
                "settings": sound_settings.describe(sound.settings),
            }
            if warning is not None:
                entry["warning"] = warning
            results.append(entry)
    return results


def _finish_and_import(
    root: Path,
    kind: str,
    name: str,
    loop: bool,
    stored_wav: Path,
    settings: FinishSettings,
    scratch: Path,
    runner: GodotRunner | None,
    encoder: FfmpegRunner | None,
    *,
    replace: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Finish ``stored_wav`` into ``scratch`` when enabled, then import the game copy from it.

    Returns the finish report (``{"applied": false}`` when finishing is off) and the import result.
    ``encoder`` is used only for music, which encodes whichever WAV the finish produced.
    """
    if settings.finish:
        source = scratch / f"{name}.wav"
        report = finish_wav(stored_wav, source, settings, loop)
    else:
        source = stored_wav
        report = {"applied": False}
    if kind == "sfx":
        imported = godot_import.import_wav(root, source, name, loop, runner, replace=replace)
    else:
        imported = godot_import.import_ogg(
            root, source, name, loop, runner, encoder, replace=replace
        )
    return report, imported


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


def _asset_exists(target: Path) -> AudioError:
    return AudioError(
        code="audio.asset_exists",
        message=f"{target} already exists",
        remediation="Choose another name, or delete the existing WAV if you mean to replace it. "
        "Overwriting an imported sound with a different file is not supported; importing the same "
        "file again re-finishes it.",
    )


def _unknown_sound(message: str, remediation: str) -> AudioError:
    return AudioError(code=UNKNOWN_SOUND, message=message, remediation=remediation)
