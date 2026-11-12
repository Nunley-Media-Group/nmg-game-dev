"""Store one audio file as a 16-bit PCM WAV under SourceArt (#155 FR3, AC1, AC2, AC6).

A ``.wav`` input is checked with the stdlib ``wave`` module and copied byte for byte. ``.mp3``,
``.ogg``, and ``.flac`` are decoded in process with ``miniaudio`` at their own sample rate and
channel count, then written as 16-bit PCM. Decoding finishes before anything is written, and each
write goes to a ``.tmp`` sibling that ``os.replace`` moves into place, so a failure leaves no file.
"""

from __future__ import annotations

import os
import shutil
import sys
import wave
from array import array
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import miniaudio

from nmg_game_dev.audio.errors import AudioError

_DECODE_REMEDIATION: Final = (
    "The file could not be decoded. Re-export it from ElevenLabs as WAV, MP3, OGG, or FLAC, or "
    "check that the file is not truncated, then import it again."
)
_SAMPLE_WIDTH_BYTES: Final = 2
_DECODE_ERRORS: Final = (miniaudio.DecodeError, wave.Error, EOFError)


def store_wav(src: Path, dest: Path) -> dict[str, Any]:
    """Write ``src`` to ``dest`` as WAV and describe it.

    Returns ``converted``, ``source_format``, ``sample_rate``, ``channels``, and
    ``duration_seconds``. Raises ``audio.decode_failed`` when the input cannot be read as audio.
    """
    source_format = src.suffix.lower().lstrip(".")
    if source_format == "wav":
        return _copy_wav(src, dest)
    return _convert(src, dest, source_format)


def _copy_wav(src: Path, dest: Path) -> dict[str, Any]:
    try:
        with wave.open(str(src), "rb") as reader:
            channels = reader.getnchannels()
            sample_rate = reader.getframerate()
            frames = reader.getnframes()
    except _DECODE_ERRORS as error:
        raise _decode_failed(src, error) from error
    _write_atomic(dest, lambda tmp: shutil.copyfile(src, tmp))
    return _description(False, "wav", sample_rate, channels, frames)


def _convert(src: Path, dest: Path, source_format: str) -> dict[str, Any]:
    try:
        info = miniaudio.get_file_info(str(src))
        # decode_file defaults to 2 channels at 44100 Hz, so pass the source values explicitly.
        decoded = miniaudio.decode_file(
            str(src),
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=info.nchannels,
            sample_rate=info.sample_rate,
        )
    except _DECODE_ERRORS as error:
        raise _decode_failed(src, error) from error
    pcm = decoded.samples
    if sys.byteorder == "big":
        # WAV stores little-endian samples, so a big-endian host swaps the copy it writes.
        pcm = array("h", pcm)
        pcm.byteswap()
    frames = len(pcm) // decoded.nchannels

    def write(tmp: Path) -> None:
        with wave.open(str(tmp), "wb") as writer:
            writer.setnchannels(decoded.nchannels)
            writer.setsampwidth(_SAMPLE_WIDTH_BYTES)
            writer.setframerate(decoded.sample_rate)
            writer.writeframes(pcm.tobytes())

    _write_atomic(dest, write)
    return _description(True, source_format, decoded.sample_rate, decoded.nchannels, frames)


def _write_atomic(dest: Path, write: Callable[[Path], object]) -> None:
    """Create ``dest``'s folder, write a ``.tmp`` sibling, and move it into place."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        write(tmp)
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _description(
    converted: bool, source_format: str, sample_rate: int, channels: int, frames: int
) -> dict[str, Any]:
    return {
        "converted": converted,
        "source_format": source_format,
        "sample_rate": sample_rate,
        "channels": channels,
        "duration_seconds": round(frames / sample_rate, 3) if sample_rate else 0.0,
    }


def _decode_failed(src: Path, error: BaseException) -> AudioError:
    return AudioError(
        code="audio.decode_failed",
        message=f"{src.name} could not be decoded as audio: {error}",
        remediation=_DECODE_REMEDIATION,
    )
