"""Storing one audio file as WAV (#155 FR3, AC1, AC2, AC6).

WAV input is copied byte for byte. MP3, OGG, and FLAC are decoded with miniaudio at their own rate
and channel count, so the tests read each output back with the stdlib ``wave`` module and compare it
with the source. A corrupt file must leave nothing behind.
"""

from __future__ import annotations

import wave
from collections.abc import Callable
from pathlib import Path

import miniaudio
import pytest

from nmg_game_dev.audio.convert import store_wav
from nmg_game_dev.audio.errors import AudioError


def _source_info(path: Path) -> tuple[int, int]:
    info = miniaudio.get_file_info(str(path))
    return info.sample_rate, info.nchannels


@pytest.mark.parametrize(
    "fixture", ["tone.mp3", "tone.ogg", "tone.flac"], ids=["mp3", "ogg", "flac"]
)
def test_compressed_input_becomes_a_16_bit_wav_at_the_source_rate(
    tmp_path: Path, fixture_file: Callable[[str], Path], fixture: str
) -> None:
    src = fixture_file(fixture)
    dest = tmp_path / "out" / "Clip.wav"

    description = store_wav(src, dest)

    rate, channels = _source_info(src)
    assert description["converted"] is True
    assert description["source_format"] == fixture.rsplit(".", 1)[1]
    assert description["sample_rate"] == rate
    assert description["channels"] == channels
    with wave.open(str(dest), "rb") as reader:
        assert reader.getsampwidth() == 2
        assert reader.getframerate() == rate
        assert reader.getnchannels() == channels
        assert reader.getnframes() > 0
    assert not (tmp_path / "out" / "Clip.wav.tmp").exists()


def test_wav_input_is_copied_byte_for_byte(
    tmp_path: Path, fixture_file: Callable[[str], Path]
) -> None:
    src = fixture_file("tone.wav")
    dest = tmp_path / "SourceArt" / "Clip.wav"

    description = store_wav(src, dest)

    assert dest.read_bytes() == src.read_bytes()
    assert description == {
        "converted": False,
        "source_format": "wav",
        "sample_rate": 22050,
        "channels": 1,
        "duration_seconds": 0.25,
    }


def test_duration_is_frames_over_rate(tmp_path: Path, fixture_file: Callable[[str], Path]) -> None:
    description = store_wav(fixture_file("tone.ogg"), tmp_path / "Clip.wav")
    assert description["duration_seconds"] == 0.25


def test_a_corrupt_mp3_fails_with_decode_failed_and_leaves_nothing(
    tmp_path: Path, fixture_file: Callable[[str], Path]
) -> None:
    dest = tmp_path / "SourceArt" / "Audio" / "SFX" / "Clip.wav"

    with pytest.raises(AudioError) as caught:
        store_wav(fixture_file("corrupt.mp3"), dest)

    assert caught.value.code == "audio.decode_failed"
    assert caught.value.remediation
    assert not dest.exists()
    assert not dest.with_name("Clip.wav.tmp").exists()
    assert not (tmp_path / "SourceArt").exists()


def test_a_wav_that_is_not_riff_fails_with_decode_failed(tmp_path: Path) -> None:
    fake = tmp_path / "fake.wav"
    fake.write_bytes(b"this is text, not a RIFF file")
    dest = tmp_path / "out" / "Clip.wav"

    with pytest.raises(AudioError) as caught:
        store_wav(fake, dest)

    assert caught.value.code == "audio.decode_failed"
    assert not dest.exists()
    assert not dest.with_name("Clip.wav.tmp").exists()
