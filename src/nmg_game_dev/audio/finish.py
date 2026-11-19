"""Finish a stored WAV before import: trim, cut, loop-crossfade, and match loudness (#252).

``finish_wav`` reads the stored 16-bit or higher PCM WAV in ``SourceArt/Audio/``, runs the steps in
``finish`` in order, and writes a 16-bit PCM WAV at the same rate and channel count. The stored WAV
is never written here, so the source stays byte-identical. Everything is numpy, so a sound effect
needs no ffmpeg; music encodes the finished WAV afterwards.

``integrated_loudness`` implements ITU-R BS.1770-4: K-weighting, 400 ms blocks with 75 % overlap,
an absolute gate at -70 LUFS and a relative gate 10 LU below the ungated mean. The K-weighting
filter is derived for the file's own rate from the standard's analog prototypes, and it is applied
as an FFT convolution of its impulse response. Measurement is the only use of that filter, so the
truncated response is accurate well beyond the 1 LU the spec allows.
"""

from __future__ import annotations

import math
import wave
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import numpy as np

from nmg_game_dev.audio.convert import _write_atomic
from nmg_game_dev.audio.errors import AudioError
from nmg_game_dev.audio.settings import FinishSettings

TRIM_THRESHOLD_DBFS: Final = -50.0
FADE_OUT_MS: Final = 20.0
PEAK_CEILING_DBFS: Final = -1.0
ABSOLUTE_GATE_LUFS: Final = -70.0
RELATIVE_GATE_LU: Final = -10.0
BLOCK_SECONDS: Final = 0.4
BLOCK_STEP_SECONDS: Final = 0.1
_LOUDNESS_OFFSET: Final = -0.691
_IR_FRAMES: Final = 1 << 15
_CONVOLVE_BLOCK: Final = 1 << 16
_PCM_SCALE: Final = 32767.0
_UNSUPPORTED_REMEDIATION: Final = (
    "Save the sound as 8-, 16-, 24-, or 32-bit PCM WAV, or import it again from the original "
    "file so it is stored as 16-bit PCM."
)

__all__ = ["finish", "finish_wav", "integrated_loudness", "read_pcm", "write_pcm"]


# --- PCM ----------------------------------------------------------------------------------------


def read_pcm(path: Path) -> tuple[np.ndarray, int]:
    """Read a PCM WAV as float64 samples in [-1, 1], shaped (frames, channels), and its rate."""
    try:
        with wave.open(str(path), "rb") as reader:
            channels = reader.getnchannels()
            width = reader.getsampwidth()
            rate = reader.getframerate()
            frames = reader.getnframes()
            raw = reader.readframes(frames)
    except (wave.Error, EOFError) as error:
        raise AudioError(
            code="audio.decode_failed",
            message=f"{path.name} could not be read as PCM WAV: {error}",
            remediation=_UNSUPPORTED_REMEDIATION,
        ) from error
    samples = _unpack(raw, width)
    return samples.reshape(-1, channels), rate


def _unpack(raw: bytes, width: int) -> np.ndarray:
    if width == 1:
        return (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    if width == 2:
        return np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if width == 3:
        octets = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int64)
        value = octets[:, 0] | (octets[:, 1] << 8) | (octets[:, 2] << 16)
        value = np.where(value >= 1 << 23, value - (1 << 24), value)
        return value.astype(np.float64) / float(1 << 23)
    if width == 4:
        return np.frombuffer(raw, dtype="<i4").astype(np.float64) / float(1 << 31)
    raise AudioError(
        code="audio.decode_failed",
        message=f"sample width {width} bytes is not a supported PCM width",
        remediation=_UNSUPPORTED_REMEDIATION,
    )


def write_pcm(path: Path, samples: np.ndarray, rate: int) -> None:
    """Write (frames, channels) samples as 16-bit PCM, rounding and clipping to [-1, 1]."""
    channels = samples.shape[1]
    pcm = np.rint(np.clip(samples, -1.0, 1.0) * _PCM_SCALE).astype("<i2")

    def write(tmp: Path) -> None:
        with wave.open(str(tmp), "wb") as writer:
            writer.setnchannels(channels)
            writer.setsampwidth(2)
            writer.setframerate(rate)
            writer.writeframes(pcm.tobytes())

    _write_atomic(path, write)


# --- BS.1770 loudness ---------------------------------------------------------------------------


def _pre_filter_coefficients(rate: int) -> tuple[float, float, float, float, float]:
    """The K-weighting high-shelf (stage 1) as (b0, b1, b2, a1, a2), derived for ``rate``."""
    f0 = 1681.974450955533
    gain_db = 3.999843853973347
    q = 0.7071752369554196
    k = math.tan(math.pi * f0 / rate)
    vh = 10.0 ** (gain_db / 20.0)
    vb = vh**0.4996667741545416
    a0 = 1.0 + k / q + k * k
    return (
        (vh + vb * k / q + k * k) / a0,
        2.0 * (k * k - vh) / a0,
        (vh - vb * k / q + k * k) / a0,
        2.0 * (k * k - 1.0) / a0,
        (1.0 - k / q + k * k) / a0,
    )


def _rlb_coefficients(rate: int) -> tuple[float, float, float, float, float]:
    """The revised low-frequency B-curve high-pass (stage 2) as (b0, b1, b2, a1, a2)."""
    f0 = 38.13547087602444
    q = 0.5003270373238773
    k = math.tan(math.pi * f0 / rate)
    a0 = 1.0 + k / q + k * k
    return (1.0, -2.0, 1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / q + k * k) / a0)


def _biquad(samples: list[float], coefficients: tuple[float, ...]) -> list[float]:
    b0, b1, b2, a1, a2 = coefficients
    out = [0.0] * len(samples)
    x1 = x2 = y1 = y2 = 0.0
    for index, x0 in enumerate(samples):
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        out[index] = y0
        x2, x1 = x1, x0
        y2, y1 = y1, y0
    return out


@lru_cache(maxsize=8)
def _impulse_response(rate: int) -> np.ndarray:
    """The truncated impulse response of both K-weighting stages, for ``rate``."""
    response = [0.0] * _IR_FRAMES
    response[0] = 1.0
    for coefficients in (_pre_filter_coefficients(rate), _rlb_coefficients(rate)):
        response = _biquad(response, coefficients)
    return np.asarray(response, dtype=np.float64)


def _convolve_same(signal: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Causal FIR filtering by overlap-add FFT, keeping the first ``len(signal)`` output frames."""
    length = signal.shape[0]
    tail = kernel.shape[0] - 1
    nfft = 1 << (_CONVOLVE_BLOCK + tail - 1).bit_length()
    spectrum = np.fft.rfft(kernel, nfft)
    out = np.zeros(length + tail, dtype=np.float64)
    for start in range(0, length, _CONVOLVE_BLOCK):
        segment = signal[start : start + _CONVOLVE_BLOCK]
        piece = np.fft.irfft(np.fft.rfft(segment, nfft) * spectrum, nfft)
        piece = piece[: segment.shape[0] + tail]
        out[start : start + piece.shape[0]] += piece
    return out[:length]


def _gated_loudness(block_power: np.ndarray) -> float:
    """Apply the absolute and relative gates to block mean-squares and return LUFS (or -inf)."""
    with np.errstate(divide="ignore"):
        block_loudness = _LOUDNESS_OFFSET + 10.0 * np.log10(block_power)
    above_absolute = block_loudness > ABSOLUTE_GATE_LUFS
    if not above_absolute.any():
        return -math.inf
    ungated_mean = float(block_power[above_absolute].mean())
    relative_gate = _LOUDNESS_OFFSET + 10.0 * math.log10(ungated_mean) + RELATIVE_GATE_LU
    kept = above_absolute & (block_loudness > relative_gate)
    if not kept.any():
        return -math.inf
    return _LOUDNESS_OFFSET + 10.0 * math.log10(float(block_power[kept].mean()))


def integrated_loudness(samples: np.ndarray, rate: int) -> float:
    """Return the BS.1770-4 integrated loudness of (frames, channels) samples, in LUFS.

    Channels carry weight 1.0. A sound shorter than one 400 ms block is measured as one block.
    Returns ``-inf`` when every block is gated out, for example for an all-silent sound.
    """
    frames = samples.shape[0]
    if frames == 0:
        return -math.inf
    power = np.zeros(frames, dtype=np.float64)
    kernel = _impulse_response(rate)
    for channel in range(samples.shape[1]):
        weighted = _convolve_same(samples[:, channel].astype(np.float64), kernel)
        power += weighted * weighted
    block = max(1, round(BLOCK_SECONDS * rate))
    step = max(1, round(BLOCK_STEP_SECONDS * rate))
    if frames < block:
        block_power = np.array([power.mean()])
    else:
        windows = np.lib.stride_tricks.sliding_window_view(power, block)[::step]
        block_power = windows.mean(axis=1)
    return _gated_loudness(block_power)


# --- Finishing ----------------------------------------------------------------------------------


def _fade_out(samples: np.ndarray, rate: int) -> None:
    """Fade the last ``FADE_OUT_MS`` to zero linearly, in place."""
    frames = min(round(FADE_OUT_MS * rate / 1000.0), samples.shape[0])
    if frames <= 0:
        return
    ramp = np.linspace(1.0, 0.0, frames) if frames > 1 else np.zeros(1)
    samples[-frames:] *= ramp[:, None]


def _crossfade_loop(samples: np.ndarray, frames: int) -> np.ndarray:
    """Blend the tail into the head over ``frames`` so the seam is a step already in the sound."""
    head = samples[:frames]
    tail = samples[-frames:]
    weight = np.linspace(0.0, 1.0, frames)[:, None]
    blended = tail * (1.0 - weight) + head * weight
    return np.concatenate([blended, samples[frames:-frames]], axis=0)


def finish(
    samples: np.ndarray, rate: int, settings: FinishSettings, loop: bool
) -> tuple[np.ndarray, dict[str, Any]]:
    """Trim, cut, crossfade, and loudness-match (frames, channels) samples, in that order.

    A sound with no frame above -50 dBFS is silent: it is not trimmed and its loudness is not
    matched, but the cut and loop steps still apply. Loudness stops at a -1 dBFS peak, reported as
    ``loudness_capped``. Returns the finished samples and the report stored as the ``finish``
    result.
    """
    x = np.array(samples, dtype=np.float64)
    threshold = 10.0 ** (TRIM_THRESHOLD_DBFS / 20.0)
    above = np.any(np.abs(x) > threshold, axis=1)
    silent = not bool(above.any())
    trimmed = 0 if silent else int(np.argmax(above))
    if not silent:
        x = x[trimmed:]

    cut = False
    if settings.max_seconds is not None:
        keep = max(1, round(settings.max_seconds * rate))
        if keep < x.shape[0]:
            x = x[:keep]
            cut = True

    crossfaded = 0
    if loop:
        frames = min(round(settings.loop_crossfade_ms * rate / 1000.0), x.shape[0] // 4)
        if frames > 0:
            x = _crossfade_loop(x, frames)
            crossfaded = frames
    else:
        _fade_out(x, rate)

    loudness: float | None = None
    capped = False
    if not silent:
        measured = integrated_loudness(x, rate)
        if math.isfinite(measured):
            gain = 10.0 ** ((settings.loudness_lufs - measured) / 20.0)
            peak = float(np.max(np.abs(x)))
            ceiling = 10.0 ** (PEAK_CEILING_DBFS / 20.0)
            if peak * gain > ceiling:
                gain = ceiling / peak
                capped = True
            x = x * gain
            loudness = integrated_loudness(x, rate)

    report: dict[str, Any] = {
        "applied": True,
        "trimmed_ms": float(round(trimmed * 1000.0 / rate, 3)),
        "cut": cut,
        "loop_crossfade_ms": float(round(crossfaded * 1000.0 / rate, 3)),
        "loudness_lufs": None if loudness is None else float(round(loudness, 3)),
        "target_lufs": float(settings.loudness_lufs),
        "loudness_capped": capped,
        "silent": silent,
        "duration_seconds": float(round(x.shape[0] / rate, 3)),
    }
    return x, report


def finish_wav(src: Path, dest: Path, settings: FinishSettings, loop: bool) -> dict[str, Any]:
    """Finish the stored WAV ``src`` into the 16-bit PCM WAV ``dest`` and return its report."""
    samples, rate = read_pcm(src)
    finished, report = finish(samples, rate, settings, loop)
    write_pcm(dest, finished, rate)
    return report
