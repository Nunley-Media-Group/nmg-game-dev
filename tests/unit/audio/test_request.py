"""Request validation for the audio import (#155 FR2, AC5).

Each invalid case raises its code before any file is touched. The tests use a fixture WAV and a
real temporary folder, so the file-existence and extension checks run for real.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from nmg_game_dev.audio.errors import AudioError
from nmg_game_dev.audio.request import FORMATS, KINDS, NAME_RE, AudioRequest


def _request(
    file: Path, name: str = "DoorCreak", kind: str = "sfx", loop: bool = False
) -> AudioRequest:
    return AudioRequest(file=file, name=name, kind=kind, loop=loop)


def test_a_valid_request_passes(source_file: Callable[[str], Path]) -> None:
    _request(source_file("tone.wav")).validate()


def test_kinds_map_to_the_folder_names() -> None:
    assert KINDS == {"sfx": "SFX", "music": "Music"}


def test_formats_are_the_four_supported_extensions() -> None:
    assert frozenset({".wav", ".mp3", ".ogg", ".flac"}) == FORMATS


@pytest.mark.parametrize("name", ["DoorCreak", "Door1", "A", "Forest2Theme"])
def test_pascal_case_names_are_accepted(name: str) -> None:
    assert NAME_RE.fullmatch(name)


@pytest.mark.parametrize("name", ["doorCreak", "Door_Creak", "Door Creak", "1Door", "Door\n"])
def test_names_that_are_not_pascal_case_are_rejected(
    source_file: Callable[[str], Path], name: str
) -> None:
    with pytest.raises(AudioError) as caught:
        _request(source_file("tone.wav"), name=name).validate()
    assert caught.value.code == "audio.invalid_request"
    assert caught.value.remediation


@pytest.mark.parametrize("name", ["SFX_DoorCreak", "MUS_Forest"])
def test_names_with_a_reserved_prefix_are_rejected(
    source_file: Callable[[str], Path], name: str
) -> None:
    with pytest.raises(AudioError) as caught:
        _request(source_file("tone.wav"), name=name).validate()
    assert caught.value.code == "audio.invalid_request"
    assert "SFX_" in caught.value.message or "MUS_" in caught.value.message


@pytest.mark.parametrize("kind", ["voice", "SFX", "", "Music"])
def test_a_kind_other_than_sfx_or_music_is_rejected(
    source_file: Callable[[str], Path], kind: str
) -> None:
    with pytest.raises(AudioError) as caught:
        _request(source_file("tone.wav"), kind=kind).validate()
    assert caught.value.code == "audio.invalid_request"


def test_a_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(AudioError) as caught:
        _request(tmp_path / "gone.wav").validate()
    assert caught.value.code == "audio.invalid_request"
    assert "does not exist" in caught.value.message


@pytest.mark.parametrize("extension", [".m4a", ".aac", ".txt", ""])
def test_an_unsupported_extension_is_rejected(tmp_path: Path, extension: str) -> None:
    path = tmp_path / f"sound{extension}"
    path.write_bytes(b"not decoded here")
    with pytest.raises(AudioError) as caught:
        _request(path).validate()
    assert caught.value.code == "audio.unsupported_format"
    assert caught.value.remediation


def test_extensions_are_matched_case_insensitively(source_file: Callable[[str], Path]) -> None:
    upper = source_file("tone.wav").with_suffix(".WAV")
    upper.write_bytes(source_file("tone.wav").read_bytes())
    _request(upper).validate()
