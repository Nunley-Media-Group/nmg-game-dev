"""``import_audio`` end to end with the fake editor (#155 AC1-AC6, FR1, FR2).

Every test injects a ``FakeUnrealPythonClient``. The autouse guard in ``conftest.py`` makes a test
that forgets to inject one fail, so no live Unreal endpoint is ever reached.
"""

from __future__ import annotations

import wave
from collections.abc import Callable
from pathlib import Path

import miniaudio
import pytest

from nmg_game_dev.audio import AudioError, import_audio
from nmg_game_dev.audio.paths import project_root
from tests.unit.fake_unreal import FakeEditor, FakeUnrealPythonClient

SFX_WAV = "SourceArt/Audio/SFX/DoorCreak.wav"
MUSIC_WAV = "SourceArt/Audio/Music/ForestTheme.wav"


def test_a_wav_sound_effect_is_stored_and_imported(
    project: Path, source_file: Callable[[str], Path]
) -> None:
    src = source_file("tone.wav")
    client = FakeUnrealPythonClient()

    result = import_audio(src, "DoorCreak", "sfx", unreal_client=client)

    stored = project / SFX_WAV
    assert stored.read_bytes() == src.read_bytes()
    sound = client.editor.sound_wave("/Game/Audio/SFX/SW_DoorCreak")
    assert sound is not None
    assert sound.get_editor_property("looping") is False
    assert result == {
        "kind": "sfx",
        "name": "DoorCreak",
        "source_art": str(stored),
        "unreal_asset": "/Game/Audio/SFX/SW_DoorCreak",
        "converted": False,
        "source_format": "wav",
        "sample_rate": 22050,
        "channels": 1,
        "duration_seconds": 0.25,
        "looping": False,
        "imported_to_unreal": True,
    }


@pytest.mark.parametrize(
    "fixture", ["tone.mp3", "tone.ogg", "tone.flac"], ids=["mp3", "ogg", "flac"]
)
def test_compressed_music_is_converted_and_imported(
    project: Path, source_file: Callable[[str], Path], fixture: str
) -> None:
    src = source_file(fixture)
    client = FakeUnrealPythonClient()

    result = import_audio(src, "ForestTheme", "music", unreal_client=client)

    info = miniaudio.get_file_info(str(src))
    stored = project / MUSIC_WAV
    with wave.open(str(stored), "rb") as reader:
        assert reader.getsampwidth() == 2
        assert reader.getframerate() == info.sample_rate
        assert reader.getnchannels() == info.nchannels
    assert result["converted"] is True
    assert result["source_format"] == fixture.rsplit(".", 1)[1]
    assert result["unreal_asset"] == "/Game/Audio/Music/SW_ForestTheme"
    assert result["sample_rate"] == info.sample_rate
    assert result["channels"] == info.nchannels
    assert result["imported_to_unreal"] is True
    assert client.editor.sound_wave("/Game/Audio/Music/SW_ForestTheme") is not None


def test_loop_true_makes_the_soundwave_loop(
    project: Path, source_file: Callable[[str], Path]
) -> None:
    client = FakeUnrealPythonClient()

    result = import_audio(source_file("tone.wav"), "DoorCreak", "sfx", True, unreal_client=client)

    sound = client.editor.sound_wave("/Game/Audio/SFX/SW_DoorCreak")
    assert sound is not None
    assert sound.get_editor_property("looping") is True
    assert result["looping"] is True


def test_loop_defaults_to_off(project: Path, source_file: Callable[[str], Path]) -> None:
    client = FakeUnrealPythonClient()

    result = import_audio(source_file("tone.mp3"), "ForestTheme", "music", unreal_client=client)

    assert result["looping"] is False


def test_an_unreachable_editor_keeps_the_file_and_warns(
    project: Path, source_file: Callable[[str], Path]
) -> None:
    client = FakeUnrealPythonClient(reachable=False)

    result = import_audio(source_file("tone.wav"), "DoorCreak", "sfx", unreal_client=client)

    assert result["imported_to_unreal"] is False
    assert result["source_art"] == str(project / SFX_WAV)
    assert result["warning"]["code"] == "mcp.unreal.unreachable"
    assert result["warning"]["remediation"]
    assert (project / SFX_WAV).is_file()
    assert client.editor.assets == {}


def test_an_import_failure_keeps_the_wav_and_propagates(
    project: Path, source_file: Callable[[str], Path]
) -> None:
    src = source_file("tone.wav")
    editor = FakeEditor()
    editor.assets["/Game/Audio/SFX/SW_DoorCreak"] = object()
    client = FakeUnrealPythonClient(editor)

    with pytest.raises(AudioError) as caught:
        import_audio(src, "DoorCreak", "sfx", unreal_client=client)

    assert caught.value.code == "audio.import_failed"
    assert (project / SFX_WAV).is_file()


def test_the_project_root_comes_from_claude_project_dir(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert project_root() == project
    monkeypatch.delenv("CLAUDE_PROJECT_DIR")
    assert project_root() == Path.cwd()


def test_an_explicit_project_root_wins(tmp_path: Path, source_file: Callable[[str], Path]) -> None:
    root = tmp_path / "elsewhere"
    client = FakeUnrealPythonClient()

    result = import_audio(
        source_file("tone.wav"), "DoorCreak", "sfx", project_root=root, unreal_client=client
    )

    assert result["source_art"] == str(root / SFX_WAV)
    assert (root / SFX_WAV).is_file()


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
    client = FakeUnrealPythonClient()

    with pytest.raises(AudioError) as caught:
        import_audio(src, name, kind, unreal_client=client)

    assert caught.value.code == code
    assert not (project / "SourceArt").exists()
    assert client.codes == []


def test_an_existing_target_is_rejected_and_left_alone(
    project: Path, source_file: Callable[[str], Path]
) -> None:
    existing = project / SFX_WAV
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"already here")
    client = FakeUnrealPythonClient()

    with pytest.raises(AudioError) as caught:
        import_audio(source_file("tone.wav"), "DoorCreak", "sfx", unreal_client=client)

    assert caught.value.code == "audio.asset_exists"
    assert caught.value.remediation
    assert existing.read_bytes() == b"already here"
    assert client.codes == []


def test_a_corrupt_mp3_fails_cleanly_with_no_unreal_call(
    project: Path, fixture_file: Callable[[str], Path], tmp_path: Path
) -> None:
    src = tmp_path / "corrupt.mp3"
    src.write_bytes(fixture_file("corrupt.mp3").read_bytes())
    client = FakeUnrealPythonClient()

    with pytest.raises(AudioError) as caught:
        import_audio(src, "ForestTheme", "music", unreal_client=client)

    assert caught.value.code == "audio.decode_failed"
    folder = project / "SourceArt" / "Audio" / "Music"
    assert not (folder / "ForestTheme.wav").exists()
    assert not (folder / "ForestTheme.wav.tmp").exists()
    assert client.codes == []
