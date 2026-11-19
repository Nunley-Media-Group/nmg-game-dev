"""The finishing steps in ``nmg_game_dev.audio.finish`` (#252 AC1-AC5, FR5).

Every signal is generated in memory, so no fixture file or binary is needed. ``integrated_loudness``
is checked against the ITU-R BS.1770-4 reference: its 48 kHz K-weighting coefficients and a
full-scale 1 kHz sine, which measures -3.01 LUFS.
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np
import pytest

from nmg_game_dev.audio.finish import (
    _pre_filter_coefficients,
    _rlb_coefficients,
    finish,
    finish_wav,
    integrated_loudness,
    read_pcm,
    write_pcm,
)
from nmg_game_dev.audio.settings import FinishSettings
from tests.unit.audio.conftest import read_wav_float, sine, write_wav

RATE = 22050
ONE_KHZ_FULL_SCALE_LUFS = -3.01
# A 1 kHz sine of amplitude A measures about this much (K-weighting is near unity at 1 kHz).
SINE_OFFSET_LUFS = ONE_KHZ_FULL_SCALE_LUFS - 20.0 * math.log10(1.0)


def _settings(lufs: float = -16.0, **kwargs: object) -> FinishSettings:
    return FinishSettings(loudness_lufs=lufs, **kwargs)  # type: ignore[arg-type]


def _amplitude_for(lufs: float) -> float:
    return float(10.0 ** ((lufs - SINE_OFFSET_LUFS) / 20.0))


def test_the_k_weighting_coefficients_match_bs1770_at_48_khz() -> None:
    # BS.1770-4 Annex 1, Table 1, 48 kHz: stage 1 (pre-filter) and stage 2 (RLB high-pass).
    pre = _pre_filter_coefficients(48000)
    rlb = _rlb_coefficients(48000)
    expected_pre = (
        1.53512485958697,
        -2.69169618940638,
        1.19839281085285,
        -1.69065929318241,
        0.73248077421585,
    )
    expected_rlb = (1.0, -2.0, 1.0, -1.99004745483398, 0.99007225036621)
    assert pre == pytest.approx(expected_pre, abs=1e-9)
    assert rlb == pytest.approx(expected_rlb, abs=1e-9)


def test_a_full_scale_1_khz_sine_measures_minus_3_01_lufs() -> None:
    tone = sine(10.0, 48000, freq=1000.0, amplitude=1.0)

    measured = integrated_loudness(tone, 48000)

    assert abs(measured - ONE_KHZ_FULL_SCALE_LUFS) <= 0.1


def test_silence_has_no_loudness() -> None:
    assert integrated_loudness(np.zeros((RATE, 1)), RATE) == -math.inf


def test_a_sound_shorter_than_one_block_is_measured_as_one_block() -> None:
    tone = sine(0.25, RATE, freq=1000.0, amplitude=0.5)

    measured = integrated_loudness(tone, RATE)

    assert measured == pytest.approx(SINE_OFFSET_LUFS + 20.0 * math.log10(0.5), abs=0.1)


def test_leading_silence_is_trimmed_so_the_sound_starts_within_10_ms_of_the_tone() -> None:
    silence = np.zeros((round(0.4 * RATE), 1))
    tone = sine(0.5, RATE, freq=440.0, amplitude=0.5)
    samples = np.concatenate([silence, tone], axis=0)

    out, report = finish(samples, RATE, _settings(), loop=False)

    threshold = 10.0 ** (-50.0 / 20.0)
    first_loud = int(np.argmax(np.abs(out[:, 0]) > threshold))
    assert first_loud / RATE <= 0.010
    assert report["trimmed_ms"] == pytest.approx(400.0, abs=0.1)
    assert report["silent"] is False


def test_an_all_silent_sound_is_not_trimmed_and_reports_silent() -> None:
    samples = np.zeros((RATE // 2, 1))

    out, report = finish(samples, RATE, _settings(), loop=False)

    assert out.shape == samples.shape
    assert not out.any()
    assert report["silent"] is True
    assert report["trimmed_ms"] == 0.0
    assert report["loudness_lufs"] is None


def _leading_frames_below_threshold(samples: np.ndarray) -> int:
    """The frames trimming removes: those before the first sample above -50 dBFS."""
    threshold = 10.0 ** (-50.0 / 20.0)
    return int(np.argmax(np.any(np.abs(samples) > threshold, axis=1)))


def test_max_seconds_keeps_that_many_frames_and_fades_the_last_20_ms_to_zero() -> None:
    samples = sine(4.0, RATE, freq=440.0, amplitude=0.5)
    # The sine starts at zero, so trimming drops its first frame before the cut is taken.
    source = samples[_leading_frames_below_threshold(samples) :, 0]
    cut = round(1.5 * RATE)

    out, report = finish(samples, RATE, _settings(max_seconds=1.5), loop=False)

    fade = round(0.020 * RATE)
    assert out.shape[0] == cut
    assert report["cut"] is True
    assert out[-1, 0] == 0.0
    # The fade is linear, and the loudness gain is one scale factor over the whole sound. So the
    # output is g * (cut signal * ramp) for one g, which a least-squares gain recovers exactly.
    ramp = np.linspace(1.0, 0.0, fade)
    shaped = source[cut - fade : cut] * ramp
    gain = float(np.dot(out[-fade:, 0], shaped) / np.dot(shaped, shaped))
    assert np.allclose(out[-fade:, 0], gain * shaped, atol=1e-9)
    assert np.allclose(out[:-fade, 0], gain * source[: cut - fade], atol=1e-9)


def test_a_loop_crossfade_makes_the_seam_no_larger_than_an_internal_step() -> None:
    samples = sine(0.25, RATE, freq=440.0, amplitude=0.5)
    assert samples[0, 0] != samples[-1, 0]

    out, report = finish(samples, RATE, _settings(), loop=True)

    internal = np.abs(np.diff(out[:, 0])).max()
    seam = abs(out[0, 0] - out[-1, 0])
    assert seam <= internal
    trimmed = samples.shape[0] - _leading_frames_below_threshold(samples)
    crossfade = min(round(500 * RATE / 1000), trimmed // 4)
    assert report["loop_crossfade_ms"] == pytest.approx(round(crossfade * 1000 / RATE, 3))


def test_the_loop_crossfade_is_capped_at_a_quarter_of_the_sound() -> None:
    samples = sine(0.25, RATE, freq=440.0, amplitude=0.5)
    quarter = samples.shape[0] // 4

    out, _ = finish(samples, RATE, _settings(loop_crossfade_ms=5000), loop=True)

    assert out.shape[0] == samples.shape[0] - quarter


def test_loudness_reaches_the_sfx_and_music_targets_within_a_tenth_of_a_unit() -> None:
    for input_lufs in (-30.0, -6.0):
        samples = sine(2.0, RATE, freq=1000.0, amplitude=_amplitude_for(input_lufs))
        for target in (-16.0, -18.0):
            out, report = finish(samples, RATE, _settings(lufs=target), loop=False)

            measured = integrated_loudness(out, RATE)
            assert measured == pytest.approx(target, abs=0.1)
            assert report["loudness_lufs"] == pytest.approx(target, abs=0.1)
            assert report["loudness_capped"] is False


def test_a_peak_ceiling_stops_the_gain_at_minus_1_dbfs_and_reports_capped() -> None:
    # A quiet tone with one loud frame: reaching -16 LUFS would push that frame past -1 dBFS.
    samples = sine(1.0, RATE, freq=1000.0, amplitude=_amplitude_for(-37.0))
    samples[RATE // 2, 0] = 0.9

    out, report = finish(samples, RATE, _settings(lufs=-16.0), loop=False)

    ceiling = 10.0 ** (-1.0 / 20.0)
    assert report["loudness_capped"] is True
    assert float(np.max(np.abs(out))) == pytest.approx(ceiling, rel=1e-9)
    assert report["loudness_lufs"] < -16.0


def test_finishing_is_byte_identical_for_identical_input_and_settings(tmp_path: Path) -> None:
    source = write_wav(tmp_path / "src.wav", sine(1.5, RATE, freq=660.0, amplitude=0.3), RATE)

    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    finish_wav(source, first, _settings(max_seconds=1.0), loop=False)
    finish_wav(source, second, _settings(max_seconds=1.0), loop=False)

    assert first.read_bytes() == second.read_bytes()


def test_finish_wav_keeps_the_rate_and_channels_of_a_stereo_source(tmp_path: Path) -> None:
    stereo = sine(0.5, 44100, freq=500.0, amplitude=0.2, channels=2)
    source = write_wav(tmp_path / "stereo.wav", stereo, 44100)

    report = finish_wav(source, tmp_path / "out.wav", _settings(), loop=False)

    samples, rate = read_wav_float(tmp_path / "out.wav")
    assert rate == 44100
    assert samples.shape[1] == 2
    assert report["applied"] is True
    assert report["loudness_lufs"] == pytest.approx(-16.0, abs=0.1)


def test_read_pcm_decodes_8_24_and_32_bit_samples(tmp_path: Path) -> None:
    cases = {
        1: (b"\x80\xff\x00", [0.0, 127.0 / 128.0, -1.0]),
        3: (
            (0).to_bytes(3, "little") + (2**23 - 1).to_bytes(3, "little") + bytes([0, 0, 0x80]),
            [0.0, (2**23 - 1) / 2**23, -1.0],
        ),
        4: (
            (0).to_bytes(4, "little", signed=True)
            + (2**31 - 1).to_bytes(4, "little", signed=True)
            + (-(2**31)).to_bytes(4, "little", signed=True),
            [0.0, (2**31 - 1) / 2**31, -1.0],
        ),
    }
    for width, (raw, expected) in cases.items():
        path = tmp_path / f"w{width}.wav"
        with wave.open(str(path), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(width)
            writer.setframerate(RATE)
            writer.writeframes(raw)

        samples, rate = read_pcm(path)

        assert rate == RATE
        assert samples[:, 0].tolist() == pytest.approx(expected, abs=1e-9)


def test_write_pcm_clips_to_full_scale(tmp_path: Path) -> None:
    path = tmp_path / "clip.wav"

    write_pcm(path, np.array([[1.5], [-2.0], [0.0]]), RATE)

    samples, _ = read_wav_float(path)
    # Full scale is 32767 in 16-bit PCM, and the reader divides by 32768.
    assert samples[:, 0].tolist() == pytest.approx([32767 / 32768, -32767 / 32768, 0.0], abs=1e-9)
