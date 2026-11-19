"""``import_audio`` end to end with fake Godot and ffmpeg runners (#155, #249 AC5, FR5).

Every test injects a ``FakeGodotRunner`` and, for music, a fake ffmpeg. The autouse guard in
``conftest.py`` makes a test that forgets to inject one fail, so no real binary ever runs.
"""

from __future__ import annotations

import functools
import io
import wave
from collections.abc import Callable
from pathlib import Path

import miniaudio
import numpy as np
import pytest

from nmg_game_dev.audio import AudioError, import_audio, refinish
from nmg_game_dev.audio.ffmpeg import resolve_ffmpeg
from nmg_game_dev.audio.finish import integrated_loudness
from nmg_game_dev.audio.paths import project_root
from nmg_game_dev.godot.project import parse_config
from nmg_game_dev.pipeline.errors import PipelineError
from tests.godot_fakes import FakeGodotRunner
from tests.unit.audio.conftest import (
    OGG_STUB,
    FakeFfmpeg,
    read_wav_float,
    sine,
    write_wav,
)

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
    # The game copy is the finished WAV (#252): not the source bytes, but the same rate.
    game_samples, game_rate = read_wav_float(project / SFX_GAME)
    assert game_rate == 22050
    assert game_samples.shape[1] == 1
    assert result["finish"]["applied"] is True
    assert result["finish"]["loudness_lufs"] == pytest.approx(-16.0, abs=0.1)
    config = _import_config(project / SFX_GAME)
    assert config[("remap", "importer")] == '"wav"'
    assert config[("remap", "type")] == '"AudioStreamWAV"'
    assert config[("params", "edit/loop_mode")] == "1"
    assert godot.calls[0] == ["--import"]
    assert godot.projects[0] == project / "game"
    assert godot.params == [{"stream": "res://assets/Audio/DoorCreak.wav"}]
    assert {key: result[key] for key in result if key not in {"finish"}} == {
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
        "settings": {
            "finish": True,
            "max_seconds": None,
            "loudness_lufs": -16.0,
            "loop_crossfade_ms": 500,
        },
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
    # ffmpeg encodes the finished WAV in the scratch folder, not the stored source (#252 FR1).
    assert call[:-1] == ["-i", call[1], "-c:a", "libvorbis", "-q:a", "5"]
    assert call[1] != str(stored)
    assert Path(call[1]).name == "ForestTheme.wav"
    [encoded_input] = ffmpeg.inputs
    with wave.open(io.BytesIO(encoded_input), "rb") as finished:
        assert finished.getsampwidth() == 2
        assert finished.getframerate() == info.sample_rate
        assert finished.getnchannels() == info.nchannels
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


# --- Finishing (#252) ----------------------------------------------------------------------------

RATE = 22050
SFX_STORED = "SourceArt/Audio/SFX/Door.wav"
SFX_GAME_DOOR = "game/assets/Audio/Door.wav"
_ONE_KHZ_OFFSET_LUFS = 3.0036  # a 1 kHz sine of amplitude A measures -3.0036 + 20 log10(A) LUFS


def _saved_wav(tmp_path: Path, name: str, samples: np.ndarray, rate: int = RATE) -> Path:
    return write_wav(tmp_path / "saved" / name, samples, rate)


def _float_samples(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data), "rb") as reader:
        channels = reader.getnchannels()
        rate = reader.getframerate()
        raw = reader.readframes(reader.getnframes())
    values = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    return values.reshape(-1, channels), rate


def test_leading_silence_is_trimmed_from_the_game_copy_and_the_source_is_kept(
    project: Path, tmp_path: Path, godot: FakeGodotRunner
) -> None:
    silence = np.zeros((round(0.4 * RATE), 1))
    src = _saved_wav(tmp_path, "Chime.wav", np.concatenate([silence, sine(0.5, RATE, 440.0, 0.5)]))
    original = src.read_bytes()

    import_audio(src, "Chime", "sfx", godot=godot)

    assert (project / "SourceArt/Audio/SFX/Chime.wav").read_bytes() == original
    samples, _ = read_wav_float(project / "game/assets/Audio/Chime.wav")
    first_loud = int(np.argmax(np.abs(samples[:, 0]) > 10.0 ** (-50.0 / 20.0)))
    assert first_loud / RATE <= 0.010


def test_a_sound_is_cut_to_max_seconds_and_fades_out(
    project: Path, tmp_path: Path, godot: FakeGodotRunner
) -> None:
    src = _saved_wav(tmp_path, "Whoosh.wav", sine(4.0, RATE, 440.0, 0.5))

    result = import_audio(src, "Whoosh", "sfx", max_seconds=1.5, godot=godot)

    samples, rate = read_wav_float(project / "game/assets/Audio/Whoosh.wav")
    assert abs(samples.shape[0] / rate - 1.5) <= 0.010
    assert samples[-1, 0] == 0.0
    fade = round(0.020 * rate)
    assert np.abs(samples[-fade:, 0]).max() < np.abs(samples[-2 * fade : -fade, 0]).max()
    assert result["finish"]["cut"] is True


@pytest.mark.parametrize("input_lufs", [-30.0, -6.0], ids=["quiet", "loud"])
def test_sfx_loudness_lands_at_minus_16_lufs(
    project: Path, tmp_path: Path, godot: FakeGodotRunner, input_lufs: float
) -> None:
    amplitude = 10.0 ** ((input_lufs + _ONE_KHZ_OFFSET_LUFS) / 20.0)
    src = _saved_wav(tmp_path, "Beep.wav", sine(2.0, RATE, 1000.0, amplitude))

    result = import_audio(src, "Beep", "sfx", godot=godot)

    samples, rate = read_wav_float(project / "game/assets/Audio/Beep.wav")
    assert integrated_loudness(samples, rate) == pytest.approx(-16.0, abs=1.0)
    assert result["finish"]["loudness_capped"] is False


def test_music_loudness_lands_at_minus_18_lufs_in_the_wav_handed_to_the_encoder(
    project: Path, tmp_path: Path, godot: FakeGodotRunner, ffmpeg: FakeFfmpeg
) -> None:
    src = _saved_wav(tmp_path, "Theme.wav", sine(2.0, RATE, 1000.0, 0.05))

    import_audio(src, "ForestTheme", "music", godot=godot, ffmpeg=ffmpeg)

    [encoded] = ffmpeg.inputs
    samples, rate = _float_samples(encoded)
    assert integrated_loudness(samples, rate) == pytest.approx(-18.0, abs=1.0)


def test_a_peak_ceiling_caps_the_gain_and_reports_it(
    project: Path, tmp_path: Path, godot: FakeGodotRunner
) -> None:
    samples = sine(1.0, RATE, 1000.0, 10.0 ** ((-37.0 + _ONE_KHZ_OFFSET_LUFS) / 20.0))
    samples[RATE // 2, 0] = 0.9
    src = _saved_wav(tmp_path, "Click.wav", samples)

    result = import_audio(src, "Click", "sfx", godot=godot)

    out, _ = read_wav_float(project / "game/assets/Audio/Click.wav")
    assert result["finish"]["loudness_capped"] is True
    assert float(np.abs(out).max()) <= 10.0 ** (-1.0 / 20.0) + 1e-4


def test_a_loop_is_crossfaded_so_its_seam_step_is_no_larger_than_an_internal_step(
    project: Path, tmp_path: Path, godot: FakeGodotRunner
) -> None:
    src = _saved_wav(tmp_path, "Hum.wav", sine(0.25, RATE, 440.0, 0.5))

    import_audio(src, "Hum", "sfx", loop=True, godot=godot)

    x = read_wav_float(project / "game/assets/Audio/Hum.wav")[0][:, 0]
    internal = np.abs(np.diff(x)).max()
    assert abs(x[0] - x[-1]) <= internal


def test_a_byte_identical_reimport_finishes_the_same_game_copy_with_stored_settings(
    project: Path, tmp_path: Path, godot: FakeGodotRunner
) -> None:
    src = _saved_wav(tmp_path, "Door.wav", sine(1.0, RATE, 660.0, 0.3))
    import_audio(src, "Door", "sfx", max_seconds=0.5, godot=godot)
    game = project / SFX_GAME_DOOR
    first = game.read_bytes()
    again = tmp_path / "again" / "Door.wav"
    again.parent.mkdir()
    again.write_bytes(src.read_bytes())

    result = import_audio(again, "Door", "sfx", godot=godot)

    assert game.read_bytes() == first
    assert result["settings"]["max_seconds"] == 0.5
    assert result["finish"]["cut"] is True


def test_a_different_source_under_the_same_name_still_fails_asset_exists(
    project: Path, tmp_path: Path, godot: FakeGodotRunner
) -> None:
    src = _saved_wav(tmp_path, "Door.wav", sine(1.0, RATE, 660.0, 0.3))
    import_audio(src, "Door", "sfx", godot=godot)
    stored = (project / SFX_STORED).read_bytes()
    other = _saved_wav(tmp_path / "other", "Door.wav", sine(1.0, RATE, 330.0, 0.3))

    with pytest.raises(AudioError) as caught:
        import_audio(other, "Door", "sfx", godot=godot)

    assert caught.value.code == "audio.asset_exists"
    assert (project / SFX_STORED).read_bytes() == stored


def test_refinish_all_rebuilds_deleted_game_copies_byte_for_byte(
    project: Path, tmp_path: Path, godot: FakeGodotRunner
) -> None:
    import_audio(
        _saved_wav(tmp_path, "Door.wav", sine(1.0, RATE, 660.0, 0.3)),
        "Door",
        "sfx",
        max_seconds=0.5,
        godot=godot,
    )
    import_audio(
        _saved_wav(tmp_path, "Hum.wav", sine(0.25, RATE, 440.0, 0.5)),
        "Hum",
        "sfx",
        loop=True,
        godot=godot,
    )
    before = {
        name: (project / f"game/assets/Audio/{name}.wav").read_bytes() for name in ("Door", "Hum")
    }
    for name in ("Door", "Hum"):
        (project / f"game/assets/Audio/{name}.wav").unlink()
        (project / f"game/assets/Audio/{name}.wav.import").unlink()

    results = refinish(None, project_root=project, godot=godot)

    assert [entry["name"] for entry in results] == ["Door", "Hum"]
    for name, data in before.items():
        assert (project / f"game/assets/Audio/{name}.wav").read_bytes() == data
    assert results[1]["looping"] is True


def test_refinish_a_named_sound_and_reject_an_unknown_name(
    project: Path, tmp_path: Path, godot: FakeGodotRunner
) -> None:
    import_audio(
        _saved_wav(tmp_path, "Door.wav", sine(1.0, RATE, 660.0, 0.3)), "Door", "sfx", godot=godot
    )

    [entry] = refinish(["Door"], project_root=project, godot=godot)

    assert entry["name"] == "Door"
    with pytest.raises(AudioError) as caught:
        refinish(["Nope"], project_root=project, godot=godot)
    assert caught.value.code == "audio.unknown_sound"


def test_refinish_without_the_stored_wav_is_unknown_sound(
    project: Path, tmp_path: Path, godot: FakeGodotRunner
) -> None:
    import_audio(
        _saved_wav(tmp_path, "Door.wav", sine(1.0, RATE, 660.0, 0.3)), "Door", "sfx", godot=godot
    )
    (project / SFX_STORED).unlink()

    with pytest.raises(AudioError) as caught:
        refinish(None, project_root=project, godot=godot)

    assert caught.value.code == "audio.unknown_sound"
    assert caught.value.remediation


def test_finish_false_copies_the_stored_wav_and_is_stored_per_sound(
    project: Path, tmp_path: Path, godot: FakeGodotRunner
) -> None:
    silence = np.zeros((round(0.4 * RATE), 1))
    src = _saved_wav(tmp_path, "Chime.wav", np.concatenate([silence, sine(0.5, RATE, 440.0, 0.5)]))

    result = import_audio(src, "Chime", "sfx", finish=False, godot=godot)

    assert (project / "SourceArt/Audio/SFX/Chime.wav").read_bytes() == (
        project / "game/assets/Audio/Chime.wav"
    ).read_bytes()
    assert result["finish"] == {"applied": False}
    stored = project / "SourceArt/Audio/audio.json"
    assert '"finish": false' in stored.read_text(encoding="utf-8")


def test_finish_false_encodes_music_from_the_stored_wav(
    project: Path, tmp_path: Path, godot: FakeGodotRunner, ffmpeg: FakeFfmpeg
) -> None:
    src = _saved_wav(tmp_path, "Theme.wav", sine(1.0, RATE, 440.0, 0.3))

    import_audio(src, "ForestTheme", "music", finish=False, godot=godot, ffmpeg=ffmpeg)

    [encoded] = ffmpeg.inputs
    assert encoded == (project / MUSIC_WAV).read_bytes()


def test_an_invalid_setting_is_rejected_before_anything_is_written(
    project: Path, tmp_path: Path, godot: FakeGodotRunner
) -> None:
    src = _saved_wav(tmp_path, "Door.wav", sine(1.0, RATE, 660.0, 0.3))

    with pytest.raises(AudioError) as caught:
        import_audio(src, "Door", "sfx", loudness_lufs=0.0, godot=godot)

    assert caught.value.code == "audio.invalid_request"
    assert not (project / "SourceArt").exists()
    assert godot.calls == []


def test_a_malformed_audio_json_fails_before_anything_is_written(
    project: Path, tmp_path: Path, godot: FakeGodotRunner
) -> None:
    (project / "SourceArt" / "Audio").mkdir(parents=True)
    (project / "SourceArt" / "Audio" / "audio.json").write_text("{nope", encoding="utf-8")
    src = _saved_wav(tmp_path, "Door.wav", sine(1.0, RATE, 660.0, 0.3))

    with pytest.raises(AudioError) as caught:
        import_audio(src, "Door", "sfx", godot=godot)

    assert caught.value.code == "audio.settings_invalid"
    assert not (project / SFX_STORED).exists()
    assert _game_files(project) == ["project.godot"]
