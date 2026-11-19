"""``import_wav`` and ``import_ogg`` on already-stored WAVs (#249 FR5).

Conversion calls these directly, so they are exercised here without ``import_audio``: the exact
``.import`` text, a write with no Godot runner, an ffmpeg failure, and the probe check.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from nmg_game_dev.audio import import_ogg, import_wav
from nmg_game_dev.audio.errors import AudioError
from nmg_game_dev.audio.godot_import import (
    check_target,
    installed_result,
    ogg_import_text,
    wav_import_text,
)
from nmg_game_dev.godot.runner import CommandResult
from nmg_game_dev.pipeline.errors import PipelineError
from tests.godot_fakes import FakeGodotRunner
from tests.unit.audio.conftest import OGG_STUB, FakeFfmpeg

WAV_LOOPING = """\
[remap]

importer="wav"
type="AudioStreamWAV"

[deps]

source_file="res://assets/Audio/Door.wav"

[params]

force/8_bit=false
force/mono=false
force/max_rate=false
force/max_rate_hz=44100
edit/trim=false
edit/normalize=false
edit/loop_mode=2
edit/loop_begin=0
edit/loop_end=-1
"""

OGG_ONCE = """\
[remap]

importer="oggvorbisstr"
type="AudioStreamOggVorbis"

[deps]

source_file="res://assets/Audio/Theme.ogg"

[params]

loop=false
loop_offset=0
bpm=0
beat_count=0
bar_beats=4
"""


@pytest.fixture
def wav(project: Path, fixture_file: Callable[[str], Path]) -> Path:
    stored = project / "SourceArt" / "Audio" / "SFX" / "Door.wav"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(fixture_file("tone.wav").read_bytes())
    return stored


def test_the_wav_import_file_matches_what_godot_reads() -> None:
    assert wav_import_text("res://assets/Audio/Door.wav", True) == WAV_LOOPING
    once = wav_import_text("res://assets/Audio/Door.wav", False)
    assert "edit/loop_mode=1\n" in once
    assert "edit/loop_begin" not in once


def test_the_ogg_import_file_matches_what_godot_reads() -> None:
    assert ogg_import_text("res://assets/Audio/Theme.ogg", False) == OGG_ONCE
    assert "\nloop=true\n" in ogg_import_text("res://assets/Audio/Theme.ogg", True)


def test_import_wav_without_a_runner_writes_the_files_only(project: Path, wav: Path) -> None:
    result = import_wav(project, wav, "Door", True, None)

    target = project / "game" / "assets" / "Audio" / "Door.wav"
    assert result == {
        "godot_asset": "res://assets/Audio/Door.wav",
        "game_asset": str(target),
        "imported_to_godot": False,
    }
    assert target.read_bytes() == wav.read_bytes()
    assert target.with_name("Door.wav.import").read_text(encoding="utf-8") == WAV_LOOPING


def test_import_wav_imports_and_probes(project: Path, wav: Path, godot: FakeGodotRunner) -> None:
    result = import_wav(project, wav, "Door", False, godot)

    assert result["imported_to_godot"] is True
    assert godot.count("--import") == 1
    assert len(godot.probe_calls("probe_audio.gd")) == 1


def test_import_ogg_encodes_with_ffmpeg_and_imports(
    project: Path, wav: Path, godot: FakeGodotRunner, ffmpeg: FakeFfmpeg
) -> None:
    result = import_ogg(project, wav, "Theme", False, godot, ffmpeg)

    target = project / "game" / "assets" / "Audio" / "Theme.ogg"
    assert result["godot_asset"] == "res://assets/Audio/Theme.ogg"
    assert target.read_bytes() == OGG_STUB
    assert target.with_name("Theme.ogg.import").read_text(encoding="utf-8") == OGG_ONCE
    [call] = ffmpeg.calls
    assert call[:2] == ["-i", str(wav)]
    assert not Path(call[-1]).exists(), "the scratch .ogg is moved into place"


def test_an_ffmpeg_failure_writes_nothing_under_game(
    project: Path, wav: Path, godot: FakeGodotRunner
) -> None:
    broken = FakeFfmpeg(CommandResult(1, stderr="Unknown encoder 'libvorbis'\n"))

    with pytest.raises(AudioError) as caught:
        import_ogg(project, wav, "Theme", False, godot, broken)

    assert caught.value.code == "audio.encode_failed"
    assert "Unknown encoder 'libvorbis'" in caught.value.message
    assert not (project / "game" / "assets").exists() or not any(
        (project / "game" / "assets").rglob("*.*")
    )
    assert godot.calls == []


def test_import_ogg_resolves_ffmpeg_when_none_is_injected(
    project: Path, wav: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _missing() -> Path:
        raise AudioError("audio.ffmpeg_not_found", "ffmpeg was not found.", "Install ffmpeg")

    monkeypatch.setattr("nmg_game_dev.audio.godot_import.resolve_ffmpeg", _missing)

    with pytest.raises(AudioError) as caught:
        import_ogg(project, wav, "Theme", True, None)

    assert caught.value.code == "audio.ffmpeg_not_found"
    assert not (project / "game" / "assets").exists()


def test_a_wrong_loop_setting_from_the_probe_fails_and_cleans_up(
    project: Path, wav: Path, ffmpeg: FakeFfmpeg
) -> None:
    godot = FakeGodotRunner({"probe_audio.gd": {"class": "AudioStreamOggVorbis", "loop": False}})

    with pytest.raises(AudioError) as caught:
        import_ogg(project, wav, "Theme", True, godot, ffmpeg)

    assert caught.value.code == "audio.import_failed"
    audio = project / "game" / "assets" / "Audio"
    assert list(audio.iterdir()) == []


def test_an_existing_import_file_blocks_the_import(project: Path, wav: Path) -> None:
    sidecar = project / "game" / "assets" / "Audio" / "Door.wav.import"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text("keep", encoding="utf-8")

    with pytest.raises(AudioError) as caught:
        import_wav(project, wav, "Door", False, None)

    assert caught.value.code == "audio.asset_exists"
    assert sidecar.read_text(encoding="utf-8") == "keep"
    assert not (project / "game" / "assets" / "Audio" / "Door.wav").exists()


# --- installed_result: resuming after an interrupted conversion (#249 review F6) ----------------


def test_installed_result_is_none_before_any_import(project: Path) -> None:
    assert installed_result(project, "sfx", "Door", False, None) is None


def test_installed_result_rechecks_an_earlier_import(
    project: Path, wav: Path, godot: FakeGodotRunner
) -> None:
    import_wav(project, wav, "Door", True, None)
    # Godot rewrites the rest of the .import file on import; only importer and loop must match.
    import_file = project / "game" / "assets" / "Audio" / "Door.wav.import"
    import_file.write_text(
        import_file.read_text(encoding="utf-8") + '\n[gen]\nuid="uid://abc"\n', encoding="utf-8"
    )

    result = installed_result(project, "sfx", "Door", True, godot)

    assert result == {
        "godot_asset": "res://assets/Audio/Door.wav",
        "game_asset": str(project / "game" / "assets" / "Audio" / "Door.wav"),
        "imported_to_godot": True,
    }
    assert godot.count("--import") == 1
    assert len(godot.probe_calls("probe_audio.gd")) == 1


def test_installed_result_ignores_a_different_loop_setting(project: Path, wav: Path) -> None:
    import_wav(project, wav, "Door", True, None)
    assert installed_result(project, "sfx", "Door", False, None) is None


def test_installed_result_with_a_failed_recheck_raises(
    project: Path, wav: Path, godot: FakeGodotRunner
) -> None:
    import_wav(project, wav, "Door", False, None)
    godot.import_errors = True
    with pytest.raises(PipelineError) as raised:
        installed_result(project, "sfx", "Door", False, godot)
    assert raised.value.code == "audio.import_failed"


# --- replace (#252 AC5): a byte-identical re-import overwrites its own game copy ----------------


def test_import_wav_with_replace_overwrites_the_game_copy(
    project: Path, wav: Path, fixture_file: Callable[[str], Path]
) -> None:
    import_wav(project, wav, "Door", False, None)
    replacement = project / "SourceArt" / "Audio" / "SFX" / "Other.wav"
    replacement.write_bytes(fixture_file("tone.mp3").read_bytes())

    import_wav(project, replacement, "Door", True, None, replace=True)

    target = project / "game" / "assets" / "Audio" / "Door.wav"
    assert target.read_bytes() == replacement.read_bytes()
    assert target.with_name("Door.wav.import").read_text(encoding="utf-8") == WAV_LOOPING


def test_check_target_replace_skips_the_existing_game_copy(project: Path, wav: Path) -> None:
    import_wav(project, wav, "Door", False, None)

    with pytest.raises(AudioError) as caught:
        check_target(project, "sfx", "Door")
    assert caught.value.code == "audio.asset_exists"
    assert check_target(project, "sfx", "Door", replace=True) == (
        project / "game" / "assets" / "Audio" / "Door.wav"
    )


def test_a_failed_replace_before_the_swap_keeps_the_earlier_game_copy(
    project: Path, wav: Path, godot: FakeGodotRunner, ffmpeg: FakeFfmpeg
) -> None:
    import_ogg(project, wav, "Theme", False, godot, ffmpeg)
    target = project / "game" / "assets" / "Audio" / "Theme.ogg"
    broken = FakeFfmpeg(CommandResult(1, stderr="encoder failed\n"))

    with pytest.raises(AudioError) as caught:
        import_ogg(project, wav, "Theme", False, godot, broken, replace=True)

    assert caught.value.code == "audio.encode_failed"
    assert target.read_bytes() == OGG_STUB
    assert target.with_name("Theme.ogg.import").read_text(encoding="utf-8") == OGG_ONCE
