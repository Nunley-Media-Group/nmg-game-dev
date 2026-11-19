"""Import one stored WAV into the Godot project headless (#249 FR5, AC5).

``import_wav`` copies a sound effect to ``game/assets/Audio/<Name>.wav`` and writes its
``.import`` file for Godot's ``wav`` importer (``AudioStreamWAV``). ``import_ogg`` encodes music
with ffmpeg to ``game/assets/Audio/<Name>.ogg`` and writes its ``.import`` file for the
``oggvorbisstr`` importer (``AudioStreamOggVorbis``). Both then run ``godot --import`` and
``probe_audio.gd`` and check the stream class and loop setting the probe reports.

The ``.import`` files carry the ``[remap]`` importer/type and the ``[params]`` Godot reads on its
next import; Godot fills in ``uid``, ``path`` and ``dest_files`` itself. With ``runner=None`` the
files are written and the import is left to the next time Godot opens the project. Any failure
after the first write removes the files this call wrote, so a rerun starts clean. Both functions
are public so conversion can import WAVs that are already stored under ``SourceArt``.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from nmg_game_dev.audio import paths
from nmg_game_dev.audio.errors import AudioError
from nmg_game_dev.audio.ffmpeg import (
    FfmpegRunner,
    SubprocessFfmpegRunner,
    encode_ogg,
    resolve_ffmpeg,
)
from nmg_game_dev.godot.project import PROJECT_FILE, godot_string, parse_config, render_config
from nmg_game_dev.godot.runner import GodotRunner, import_project, run_probe

IMPORT_FAILED: Final = "audio.import_failed"
PROBE: Final = "probe_audio.gd"

WAV_IMPORT_LOOP_DISABLED: Final = 1
WAV_IMPORT_LOOP_FORWARD: Final = 2
"""``edit/loop_mode`` importer option values (0 detect, 1 disabled, 2 forward)."""

STREAM_LOOP_DISABLED: Final = 0
STREAM_LOOP_FORWARD: Final = 1
"""``AudioStreamWAV.loop_mode`` values the probe reports (``LOOP_DISABLED``, ``LOOP_FORWARD``)."""

_IMPORT_REMEDIATION: Final = (
    "Read the Godot error in the message and fix its cause. The stored WAV under "
    "SourceArt/Audio/ is kept, so delete it before importing the sound again under the same name, "
    "or rerun /convert-to-godot, which imports stored WAVs directly."
)

__all__ = [
    "check_target",
    "import_ogg",
    "import_wav",
    "installed_result",
    "ogg_import_text",
    "wav_import_text",
]


def wav_import_text(res_path: str, loop: bool) -> str:
    """Return the ``.import`` text for a sound effect at ``res_path``."""
    loop_entries = (
        [
            ("edit/loop_mode", str(WAV_IMPORT_LOOP_FORWARD)),
            ("edit/loop_begin", "0"),
            ("edit/loop_end", "-1"),
        ]
        if loop
        else [("edit/loop_mode", str(WAV_IMPORT_LOOP_DISABLED))]
    )
    return render_config(
        [
            (
                "remap",
                [("importer", godot_string("wav")), ("type", godot_string("AudioStreamWAV"))],
            ),
            ("deps", [("source_file", godot_string(res_path))]),
            (
                "params",
                [
                    ("force/8_bit", "false"),
                    ("force/mono", "false"),
                    ("force/max_rate", "false"),
                    ("force/max_rate_hz", "44100"),
                    ("edit/trim", "false"),
                    ("edit/normalize", "false"),
                    *loop_entries,
                ],
            ),
        ]
    )


def ogg_import_text(res_path: str, loop: bool) -> str:
    """Return the ``.import`` text for a music track at ``res_path``."""
    return render_config(
        [
            (
                "remap",
                [
                    ("importer", godot_string("oggvorbisstr")),
                    ("type", godot_string("AudioStreamOggVorbis")),
                ],
            ),
            ("deps", [("source_file", godot_string(res_path))]),
            (
                "params",
                [
                    ("loop", "true" if loop else "false"),
                    ("loop_offset", "0"),
                    ("bpm", "0"),
                    ("beat_count", "0"),
                    ("bar_beats", "4"),
                ],
            ),
        ]
    )


def import_wav(
    project_root: Path,
    wav: Path,
    name: str,
    loop: bool,
    runner: GodotRunner | None,
    replace: bool = False,
) -> dict[str, Any]:
    """Copy ``wav`` into the Godot project as a sound effect and import it as ``AudioStreamWAV``.

    Returns ``godot_asset`` (the ``res://`` path), ``game_asset`` (the file path), and
    ``imported_to_godot``. Raises ``audio.godot_project_missing``, ``audio.asset_exists``, or
    ``audio.import_failed``. With ``replace`` an existing game copy is overwritten (#252 AC5).
    """
    target = check_target(project_root, "sfx", name, replace=replace)

    def write(tmp: Path) -> None:
        shutil.copyfile(wav, tmp)

    return _install(
        project_root,
        "sfx",
        name,
        target,
        write,
        wav_import_text,
        loop,
        runner,
        _expected("sfx", loop),
    )


def import_ogg(
    project_root: Path,
    wav: Path,
    name: str,
    loop: bool,
    runner: GodotRunner | None,
    ffmpeg: FfmpegRunner | None = None,
    replace: bool = False,
) -> dict[str, Any]:
    """Encode ``wav`` to Ogg Vorbis in the Godot project and import it as ``AudioStreamOggVorbis``.

    ``ffmpeg`` defaults to the binary ``resolve_ffmpeg`` finds; a missing ffmpeg raises
    ``audio.ffmpeg_not_found`` before anything is written under ``game/``. Otherwise raises like
    ``import_wav``, plus ``audio.encode_failed``. ``replace`` works as it does for ``import_wav``.
    """
    target = check_target(project_root, "music", name, replace=replace)
    encoder = ffmpeg if ffmpeg is not None else SubprocessFfmpegRunner(resolve_ffmpeg())

    def write(tmp: Path) -> None:
        with tempfile.TemporaryDirectory(prefix="nmg-audio-") as scratch:
            encoded = Path(scratch) / f"{name}.ogg"
            encode_ogg(encoder, wav, encoded)
            shutil.move(str(encoded), str(tmp))

    return _install(
        project_root,
        "music",
        name,
        target,
        write,
        ogg_import_text,
        loop,
        runner,
        _expected("music", loop),
    )


def installed_result(
    project_root: Path, kind: str, name: str, loop: bool, runner: GodotRunner | None
) -> dict[str, Any] | None:
    """Return the result for a sound an earlier run already installed, or ``None``.

    A sound counts as installed when ``game/assets/Audio/<Name>.<wav|ogg>`` exists beside a
    ``.import`` file that selects the same importer and loop setting (Godot rewrites the rest of
    that file on import). With a runner, the import is checked again with ``godot --import`` and
    ``probe_audio.gd``, so a resumed conversion never trusts a half-finished one. Lets conversion
    resume after a crash between the import and its state update instead of failing
    ``audio.asset_exists``.
    """
    target = paths.game_asset(project_root, kind, name)
    import_file = _import_file(target)
    if not target.is_file() or not import_file.is_file():
        return None
    res = paths.godot_asset(kind, name)
    text = wav_import_text(res, loop) if kind == "sfx" else ogg_import_text(res, loop)
    wanted = parse_config(text)
    have = parse_config(import_file.read_text(encoding="utf-8"))
    loop_key = ("params", "edit/loop_mode") if kind == "sfx" else ("params", "loop")
    for key in (("remap", "importer"), loop_key):
        if have.get(key) != wanted[key]:
            return None
    if runner is not None:
        _import_and_probe(runner, paths.game_project(project_root), res, _expected(kind, loop))
    return {
        "godot_asset": res,
        "game_asset": str(target),
        "imported_to_godot": runner is not None,
    }


def _expected(kind: str, loop: bool) -> dict[str, Any]:
    """The probe result an imported sound must report."""
    if kind == "sfx":
        return {
            "class": "AudioStreamWAV",
            "loop_mode": STREAM_LOOP_FORWARD if loop else STREAM_LOOP_DISABLED,
        }
    return {"class": "AudioStreamOggVorbis", "loop": bool(loop)}


def check_target(project_root: Path, kind: str, name: str, replace: bool = False) -> Path:
    """Return the ``game/assets/Audio/`` target after checking that nothing blocks writing it.

    Raises ``audio.godot_project_missing`` without ``game/project.godot``, and
    ``audio.asset_exists`` when the target or its ``.import`` file already exists. ``replace``
    skips that last check, for a byte-identical re-import or ``refinish`` (#252 AC5).
    """
    game = paths.game_project(project_root)
    if not (game / PROJECT_FILE).is_file():
        raise AudioError(
            code="audio.godot_project_missing",
            message=f"No {PROJECT_FILE} was found at {game}.",
            remediation="Run /onboard-consumer to create game/project.godot, then import the "
            "sound again.",
        )
    target = paths.game_asset(project_root, kind, name)
    if replace:
        return target
    for path in (target, _import_file(target)):
        if path.exists():
            raise AudioError(
                code="audio.asset_exists",
                message=f"{path} already exists",
                remediation="Choose another name, or delete the existing file and its .import "
                "file if you mean to replace it. Overwriting an imported sound in place is not "
                "supported.",
            )
    return target


def _install(
    project_root: Path,
    kind: str,
    name: str,
    target: Path,
    write: Callable[[Path], None],
    import_text: Callable[[str, bool], str],
    loop: bool,
    runner: GodotRunner | None,
    expected: dict[str, Any],
) -> dict[str, Any]:
    res = paths.godot_asset(kind, name)
    import_file = _import_file(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    replaced = False
    try:
        write(tmp)
        os.replace(tmp, target)
        # From here the game copy is this call's output, so a failure removes it. Before this
        # point a failed replace leaves the earlier game copy in place.
        replaced = True
        import_file.write_text(import_text(res, loop), encoding="utf-8")
        if runner is not None:
            _import_and_probe(runner, paths.game_project(project_root), res, expected)
    except BaseException:
        tmp.unlink(missing_ok=True)
        if replaced:
            for path in (target, import_file):
                path.unlink(missing_ok=True)
        raise
    return {
        "godot_asset": res,
        "game_asset": str(target),
        "imported_to_godot": runner is not None,
    }


def _import_and_probe(
    runner: GodotRunner, project: Path, res: str, expected: dict[str, Any]
) -> None:
    import_project(runner, project, error_code=IMPORT_FAILED)
    result = run_probe(runner, project, PROBE, {"stream": res}, error_code=IMPORT_FAILED)
    actual = {key: result.get(key) for key in expected}
    if actual != expected:
        raise AudioError(
            code=IMPORT_FAILED,
            message=f"Godot imported {res} as {actual}, expected {expected}",
            remediation=_IMPORT_REMEDIATION,
        )


def _import_file(target: Path) -> Path:
    return target.with_name(target.name + ".import")
