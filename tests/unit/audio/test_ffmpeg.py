"""ffmpeg resolution and the Ogg Vorbis encode command (#249 FR5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.audio.errors import AudioError
from nmg_game_dev.audio.ffmpeg import encode_ogg_args, resolve_ffmpeg


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_ffmpeg_bin_wins_when_it_is_executable(tmp_path: Path) -> None:
    binary = _executable(tmp_path / "ffmpeg")

    assert resolve_ffmpeg({"FFMPEG_BIN": str(binary)}, lambda _name: "/usr/bin/ffmpeg") == binary


def test_a_non_executable_ffmpeg_bin_falls_back_to_path(tmp_path: Path) -> None:
    plain = tmp_path / "ffmpeg"
    plain.write_text("", encoding="utf-8")

    found = resolve_ffmpeg({"FFMPEG_BIN": str(plain)}, lambda _name: "/usr/bin/ffmpeg")

    assert found == Path("/usr/bin/ffmpeg")


def test_missing_ffmpeg_raises_with_the_remediation(tmp_path: Path) -> None:
    with pytest.raises(AudioError) as caught:
        resolve_ffmpeg({"FFMPEG_BIN": str(tmp_path / "nope")}, lambda _name: None)

    assert caught.value.code == "audio.ffmpeg_not_found"
    assert caught.value.remediation == "Install ffmpeg or set FFMPEG_BIN to its executable."
    assert "FFMPEG_BIN=" in caught.value.message
    assert "ffmpeg on PATH" in caught.value.message


def test_the_encode_command_uses_libvorbis_at_quality_five() -> None:
    args = encode_ogg_args(Path("/a/Theme.wav"), Path("/tmp/Theme.ogg"))

    assert args == ["-i", "/a/Theme.wav", "-c:a", "libvorbis", "-q:a", "5", "/tmp/Theme.ogg"]
