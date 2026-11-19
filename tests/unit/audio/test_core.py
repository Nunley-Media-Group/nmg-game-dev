"""``import_audio`` end to end with fake Godot and ffmpeg runners (#155, #249 AC5, FR5).

Every test injects a ``FakeGodotRunner`` and, for music, a fake ffmpeg. The autouse guard in
``conftest.py`` makes a test that forgets to inject one fail, so no real binary ever runs.
"""

from __future__ import annotations

import functools
import wave
from collections.abc import Callable
from pathlib import Path

import miniaudio
import pytest

from nmg_game_dev.audio import AudioError, import_audio
from nmg_game_dev.audio.ffmpeg import resolve_ffmpeg
from nmg_game_dev.audio.paths import project_root
from nmg_game_dev.godot.project import parse_config
from nmg_game_dev.pipeline.errors import PipelineError
from tests.godot_fakes import FakeGodotRunner
from tests.unit.audio.conftest import OGG_STUB, FakeFfmpeg

SFX_WAV = "SourceArt/Audio/SFX/DoorCreak.wav"
MUSIC_WAV = "SourceArt/Audio/Music/ForestTheme.wav"
SFX_GAME = "game/assets/Audio/DoorCreak.wav"
MUSIC_GAME = "game/assets/Audio/ForestTheme.ogg"


def _import_config(path: Path) -> dict[tuple[str, str], str]:
    return parse_config(path.with_name(path.name + ".import").read_text(encoding="utf-8"))


def _game_files(project: Path) -> list[str]:
    game = project / "game"
    return sorted(p.relative_to(game).as_posix() for p in game.rglob("*") if p.is_file())


def test_a_wav_sound_effect_is_stored_and_imported_as_an_audio_stream_wav(
    project: Path, source_file: Callable[[str], Path], godot: FakeGodotRunner
) -> None:
    src = source_file("tone.wav")

    result = import_audio(src, "DoorCreak", "sfx", godot=godot)

    stored = project / SFX_WAV
    assert stored.read_bytes() == src.read_bytes()
    assert (project / SFX_GAME).read_bytes() == src.read_bytes()
    config = _import_config(project / SFX_GAME)
    assert config[("remap", "importer")] == '"wav"'
    assert config[("remap", "type")] == '"AudioStreamWAV"'
    assert config[("params", "edit/loop_mode")] == "1"
    assert godot.calls[0] == ["--import"]
    assert godot.projects[0] == project / "game"
    assert godot.params == [{"stream": "res://assets/Audio/DoorCreak.wav"}]
    assert result == {
        "kind": "sfx",
        "name": "DoorCreak",
        "source_art": str(stored),
        "godot_asset": "res://assets/Audio/DoorCreak.wav",
        "converted": False,
        "source_format": "wav",
        "sample_rate": 22050,
        "channels": 1,
        "duration_seconds": 0.25,
        "looping": False,
        "imported_to_godot": True,
    }


@pytest.mark.parametrize(
    "fixture", ["tone.mp3", "tone.ogg", "tone.flac"], ids=["mp3", "ogg", "flac"]
)
def test_compressed_music_is_stored_encoded_to_ogg_and_imported(
    project: Path,
    source_file: Callable[[str], Path],
    godot: FakeGodotRunner,
    ffmpeg: FakeFfmpeg,
    fixture: str,
) -> None:
    src = source_file(fixture)

    result = import_audio(src, "ForestTheme", "music", godot=godot, ffmpeg=ffmpeg)

    info = miniaudio.get_file_info(str(src))
    stored = project / MUSIC_WAV
    with wave.open(str(stored), "rb") as reader:
        assert reader.getsampwidth() == 2
        assert reader.getframerate() == info.sample_rate
        assert reader.getnchannels() == info.nchannels
    [call] = ffmpeg.calls
    assert call[:-1] == ["-i", str(stored), "-c:a", "libvorbis", "-q:a", "5"]
    assert call[-1].endswith(".ogg")
    assert (project / MUSIC_GAME).read_bytes() == OGG_STUB
    config = _import_config(project / MUSIC_GAME)
    assert config[("remap", "importer")] == '"oggvorbisstr"'
    assert config[("remap", "type")] == '"AudioStreamOggVorbis"'
    assert config[("params", "loop")] == "false"
    assert result["converted"] is True
    assert result["source_format"] == fixture.rsplit(".", 1)[1]
    assert result["godot_asset"] == "res://assets/Audio/ForestTheme.ogg"
    assert result["sample_rate"] == info.sample_rate
    assert result["channels"] == info.nchannels
    assert result["imported_to_godot"] is True
    assert godot.params == [{"stream": "res://assets/Audio/ForestTheme.ogg"}]


def test_a_looping_sound_effect_imports_with_forward_loop(
    project: Path, source_file: Callable[[str], Path], godot: FakeGodotRunner
) -> None:
    result = import_audio(source_file("tone.wav"), "DoorCreak", "sfx", True, godot=godot)

    config = _import_config(project / SFX_GAME)
    assert config[("params", "edit/loop_mode")] == "2"
    assert config[("params", "edit/loop_begin")] == "0"
    assert config[("params", "edit/loop_end")] == "-1"
    assert result["looping"] is True


def test_looping_music_imports_with_loop_enabled(
    project: Path, source_file: Callable[[str], Path], godot: FakeGodotRunner, ffmpeg: FakeFfmpeg
) -> None:
    result = import_audio(
        source_file("tone.wav"), "ForestTheme", "music", True, godot=godot, ffmpeg=ffmpeg
    )

    assert _import_config(project / MUSIC_GAME)[("params", "loop")] == "true"
    assert result["looping"] is True


def test_loop_defaults_to_off(
    project: Path, source_file: Callable[[str], Path], godot: FakeGodotRunner, ffmpeg: FakeFfmpeg
) -> None:
    result = import_audio(
        source_file("tone.mp3"), "ForestTheme", "music", godot=godot, ffmpeg=ffmpeg
    )

    assert result["looping"] is False


def test_a_missing_godot_writes_the_files_and_warns(
    project: Path, source_file: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _not_found() -> Path:
        raise PipelineError(
            "godot.not_found",
            "Godot was not found.",
            "Install Godot 4 (latest stable) or set GODOT_BIN to its executable.",
            "godot",
        )

    monkeypatch.setattr("nmg_game_dev.audio.core.resolve_godot", _not_found)

    result = import_audio(source_file("tone.wav"), "DoorCreak", "sfx")

    assert result["imported_to_godot"] is False
    assert result["godot_asset"] == "res://assets/Audio/DoorCreak.wav"
    assert result["warning"]["code"] == "godot.not_found"
    assert result["warning"]["remediation"].startswith("Install Godot 4")
    assert (project / SFX_WAV).is_file()
    assert (project / SFX_GAME).is_file()
    assert (project / (SFX_GAME + ".import")).is_file()


def test_music_without_ffmpeg_fails_before_writing_anything(
    project: Path,
    source_file: Callable[[str], Path],
    godot: FakeGodotRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "nmg_game_dev.audio.core.resolve_ffmpeg",
        functools.partial(resolve_ffmpeg, {}, lambda _name: None),
    )

    with pytest.raises(AudioError) as caught:
        import_audio(source_file("tone.wav"), "ForestTheme", "music", godot=godot)

    assert caught.value.code == "audio.ffmpeg_not_found"
    assert caught.value.remediation == "Install ffmpeg or set FFMPEG_BIN to its executable."
    assert _game_files(project) == ["project.godot"]
    assert not (project / "SourceArt").exists()
    assert godot.calls == []


def test_a_sound_effect_needs_no_ffmpeg(
    project: Path, source_file: Callable[[str], Path], godot: FakeGodotRunner
) -> None:
    result = import_audio(source_file("tone.wav"), "DoorCreak", "sfx", godot=godot)

    assert result["imported_to_godot"] is True


def test_an_import_failure_keeps_the_stored_wav_and_removes_the_game_files(
    project: Path, source_file: Callable[[str], Path]
) -> None:
    godot = FakeGodotRunner(import_errors=True)

    with pytest.raises(PipelineError) as caught:
        import_audio(source_file("tone.wav"), "DoorCreak", "sfx", godot=godot)

    assert caught.value.code == "audio.import_failed"
    assert (project / SFX_WAV).is_file()
    assert _game_files(project) == ["project.godot"]


def test_a_probe_that_reports_the_wrong_stream_fails_the_import(
    project: Path, source_file: Callable[[str], Path]
) -> None:
    godot = FakeGodotRunner({"probe_audio.gd": {"class": "AudioStreamWAV", "loop_mode": 1}})

    with pytest.raises(AudioError) as caught:
        import_audio(source_file("tone.wav"), "DoorCreak", "sfx", godot=godot)

    assert caught.value.code == "audio.import_failed"
    assert "expected" in caught.value.message
    assert not (project / SFX_GAME).exists()


def test_the_project_root_comes_from_claude_project_dir(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert project_root() == project
    monkeypatch.delenv("CLAUDE_PROJECT_DIR")
    assert project_root() == Path.cwd()


def test_an_explicit_project_root_wins(
    tmp_path: Path, source_file: Callable[[str], Path], godot: FakeGodotRunner
) -> None:
    root = tmp_path / "elsewhere"
    (root / "game").mkdir(parents=True)
    (root / "game" / "project.godot").write_text("", encoding="utf-8")

    result = import_audio(
        source_file("tone.wav"), "DoorCreak", "sfx", project_root=root, godot=godot
    )

    assert result["source_art"] == str(root / SFX_WAV)
    assert (root / SFX_WAV).is_file()
    assert (root / SFX_GAME).is_file()


def test_a_missing_godot_project_fails_before_writing_anything(
    tmp_path: Path, source_file: Callable[[str], Path], godot: FakeGodotRunner
) -> None:
    root = tmp_path / "no-game"

    with pytest.raises(AudioError) as caught:
        import_audio(source_file("tone.wav"), "DoorCreak", "sfx", project_root=root, godot=godot)

    assert caught.value.code == "audio.godot_project_missing"
    assert "/onboard-consumer" in caught.value.remediation
    assert not root.exists()


@pytest.mark.parametrize(
    ("name", "kind", "file_name", "code"),
    [
        ("doorCreak", "sfx", "tone.wav", "audio.invalid_request"),
        ("SFX_DoorCreak", "sfx", "tone.wav", "audio.invalid_request"),
        ("DoorCreak", "voice", "tone.wav", "audio.invalid_request"),
        ("DoorCreak", "sfx", "no-such-file.wav", "audio.invalid_request"),
        ("DoorCreak", "sfx", "clip.m4a", "audio.unsupported_format"),
    ],
    ids=["bad-name", "reserved-prefix", "bad-kind", "missing-file", "bad-format"],
)
def test_invalid_requests_write_nothing_and_call_nothing(
    project: Path,
    tmp_path: Path,
    source_file: Callable[[str], Path],
    godot: FakeGodotRunner,
    name: str,
    kind: str,
    file_name: str,
    code: str,
) -> None:
    if file_name == "clip.m4a":
        src = tmp_path / file_name
        src.write_bytes(b"not decoded")
    elif file_name == "no-such-file.wav":
        src = tmp_path / file_name
    else:
        src = source_file(file_name)

    with pytest.raises(AudioError) as caught:
        import_audio(src, name, kind, godot=godot)

    assert caught.value.code == code
    assert not (project / "SourceArt").exists()
    assert _game_files(project) == ["project.godot"]
    assert godot.calls == []


def test_an_existing_source_art_target_is_rejected_and_left_alone(
    project: Path, source_file: Callable[[str], Path], godot: FakeGodotRunner
) -> None:
    existing = project / SFX_WAV
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"already here")

    with pytest.raises(AudioError) as caught:
        import_audio(source_file("tone.wav"), "DoorCreak", "sfx", godot=godot)

    assert caught.value.code == "audio.asset_exists"
    assert caught.value.remediation
    assert existing.read_bytes() == b"already here"
    assert godot.calls == []


def test_an_existing_game_asset_is_rejected_before_anything_is_stored(
    project: Path, source_file: Callable[[str], Path], godot: FakeGodotRunner, ffmpeg: FakeFfmpeg
) -> None:
    existing = project / MUSIC_GAME
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"already here")

    with pytest.raises(AudioError) as caught:
        import_audio(source_file("tone.wav"), "ForestTheme", "music", godot=godot, ffmpeg=ffmpeg)

    assert caught.value.code == "audio.asset_exists"
    assert existing.read_bytes() == b"already here"
    assert not (project / "SourceArt").exists()
    assert ffmpeg.calls == []
    assert godot.calls == []


def test_a_corrupt_mp3_fails_cleanly_with_no_godot_call(
    project: Path,
    fixture_file: Callable[[str], Path],
    tmp_path: Path,
    godot: FakeGodotRunner,
    ffmpeg: FakeFfmpeg,
) -> None:
    src = tmp_path / "corrupt.mp3"
    src.write_bytes(fixture_file("corrupt.mp3").read_bytes())

    with pytest.raises(AudioError) as caught:
        import_audio(src, "ForestTheme", "music", godot=godot, ffmpeg=ffmpeg)

    assert caught.value.code == "audio.decode_failed"
    folder = project / "SourceArt" / "Audio" / "Music"
    assert not (folder / "ForestTheme.wav").exists()
    assert not (folder / "ForestTheme.wav.tmp").exists()
    assert godot.calls == []
    assert ffmpeg.calls == []
