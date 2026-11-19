"""pytest-bdd bindings for audio_finishing.feature: SCN001-SCN007 (#252 AC1-AC7).

The sounds are generated in memory and written as WAV into a temporary project. Godot is the
``FakeGodotRunner`` from ``tests.unit.audio.conftest``, whose probe answers from the
``.import`` file the import wrote, and ffmpeg is a ``FakeFfmpeg`` that records the WAV it is
handed, so the music loudness is measured on the finished file. No real Godot or ffmpeg runs.
"""

from __future__ import annotations

import io
import json
import shutil
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from nmg_game_dev.audio import AudioError, import_audio, refinish
from nmg_game_dev.audio.finish import integrated_loudness
from nmg_game_dev.pipeline.errors import PipelineError
from tests.unit.audio.conftest import FakeFfmpeg, fake_godot, read_wav_float, sine, write_wav

scenarios("audio_finishing.feature")

RATE = 22050
_ONE_KHZ_OFFSET_LUFS = 3.0036  # a 1 kHz sine of amplitude A measures -3.0036 + 20 log10(A) LUFS
_TONE_THRESHOLD = 10.0 ** (-50.0 / 20.0)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    root = tmp_path / "project"
    (root / "game").mkdir(parents=True)
    (root / "game" / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    saved = tmp_path / "saved"
    saved.mkdir()
    values: dict[str, Any] = {
        "root": root,
        "saved": saved,
        "godot": fake_godot(),
        "ffmpeg": FakeFfmpeg(),
        "ffmpeg_installed": True,
        "src": None,
        "name": "Chime",
        "kind": "sfx",
        "loop": False,
        "result": None,
        "error": None,
        "first": None,
        "refinished": None,
    }

    def _resolve_ffmpeg() -> Path:
        if not values["ffmpeg_installed"]:
            raise AudioError(
                "audio.ffmpeg_not_found",
                "ffmpeg was not found. Tried: ffmpeg on PATH.",
                "Install ffmpeg or set FFMPEG_BIN to its executable.",
            )
        return Path("/fake/ffmpeg")

    monkeypatch.setattr("nmg_game_dev.audio.core.resolve_ffmpeg", _resolve_ffmpeg)
    monkeypatch.setattr(
        "nmg_game_dev.audio.core.SubprocessFfmpegRunner", lambda _b: values["ffmpeg"]
    )
    return values


def _amplitude_for(lufs: float) -> float:
    return float(10.0 ** ((lufs - _ONE_KHZ_OFFSET_LUFS) / 20.0))


def _save(state: dict[str, Any], filename: str, samples: np.ndarray) -> Path:
    path = write_wav(state["saved"] / filename, samples, RATE)
    state["src"] = path
    return path


def _silence_then_tone() -> np.ndarray:
    silence = np.zeros((round(0.4 * RATE), 1))
    return np.concatenate([silence, sine(0.5, RATE, 440.0, 0.5)], axis=0)


def _game_copy(state: dict[str, Any], name: str, kind: str = "sfx") -> Path:
    extension = "wav" if kind == "sfx" else "ogg"
    path: Path = state["root"] / "game" / "assets" / "Audio" / f"{name}.{extension}"
    return path


def _run(state: dict[str, Any], name: str, kind: str, loop: bool = False, **settings: Any) -> None:
    state["name"] = name
    state["kind"] = kind
    state["loop"] = loop
    state["error"] = None
    try:
        state["result"] = import_audio(
            state["src"], name, kind, loop, godot=state["godot"], **settings
        )
    except PipelineError as error:
        state["result"] = None
        state["error"] = error


def _float_samples(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data), "rb") as reader:
        channels = reader.getnchannels()
        rate = reader.getframerate()
        raw = reader.readframes(reader.getnframes())
    values = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    return values.reshape(-1, channels), rate


def _stored_settings(state: dict[str, Any]) -> dict[str, Any]:
    text = (state["root"] / "SourceArt" / "Audio" / "audio.json").read_text(encoding="utf-8")
    sounds: dict[str, Any] = json.loads(text)["sounds"]
    return sounds


# --- Given ---------------------------------------------------------------------------------------


@given("a sound effect WAV that starts with 400 ms of silence before a tone")
def _silence_before_tone(state: dict[str, Any]) -> None:
    _save(state, "Chime.wav", _silence_then_tone())


@given("a 4-second tone WAV")
def _four_second_tone(state: dict[str, Any]) -> None:
    _save(state, "Whoosh.wav", sine(4.0, RATE, 440.0, 0.5))


@given(parsers.parse("a tone WAV measuring {lufs} LUFS"))
def _tone_at(state: dict[str, Any], lufs: str) -> None:
    _save(state, "Tone.wav", sine(2.0, RATE, 1000.0, _amplitude_for(float(lufs))))


@given("a tone WAV whose last sample does not match its first")
def _mismatched_tone(state: dict[str, Any]) -> None:
    _save(state, "Hum.wav", sine(0.25, RATE, 440.0, 0.5))


@given(parsers.parse('"{name}" was imported with max_seconds {seconds}'))
def _imported_with_cut(state: dict[str, Any], name: str, seconds: str) -> None:
    _save(state, f"{name}.wav", sine(1.0, RATE, 660.0, 0.3))
    _run(state, name, "sfx", max_seconds=float(seconds))
    assert state["error"] is None, state["error"]
    state["first"] = _game_copy(state, name).read_bytes()


@given("ffmpeg is not on PATH and FFMPEG_BIN is unset")
def _no_ffmpeg(state: dict[str, Any]) -> None:
    state["ffmpeg_installed"] = False


@given("a sound effect WAV that starts with silence")
def _silent_start(state: dict[str, Any]) -> None:
    _save(state, "Chime.wav", _silence_then_tone())


# --- When ----------------------------------------------------------------------------------------


@when(parsers.parse('import_audio imports it as "{name}" with default settings'))
def _imports_default(state: dict[str, Any], name: str) -> None:
    _run(state, name, "sfx")


@when(parsers.parse('import_audio imports it as "{name}" with max_seconds {seconds}'))
def _imports_cut(state: dict[str, Any], name: str, seconds: str) -> None:
    _run(state, name, "sfx", max_seconds=float(seconds))


@when(parsers.parse('import_audio imports it as kind "{kind}" with default settings'))
def _imports_kind(state: dict[str, Any], kind: str) -> None:
    _run(state, "Sample", kind)


@when("import_audio imports it with loop true")
def _imports_looping(state: dict[str, Any]) -> None:
    _run(state, "Loop", "sfx", loop=True)


@when("import_audio imports it with finish false")
def _imports_unfinished(state: dict[str, Any]) -> None:
    _run(state, "Chime", "sfx", finish=False)


@when(
    parsers.parse(
        'the same file is imported again as "{name}" with no settings, and then refinish --all runs'
    )
)
def _reimported_then_refinished(state: dict[str, Any], name: str) -> None:
    again = state["saved"] / "again" / f"{name}.wav"
    again.parent.mkdir(exist_ok=True)
    shutil.copyfile(state["src"], again)
    state["src"] = again
    _run(state, name, "sfx")
    assert state["error"] is None, state["error"]
    state["refinished"] = refinish(None, project_root=state["root"], godot=state["godot"])


@when("import_audio imports a music file")
def _imports_music(state: dict[str, Any]) -> None:
    _save(state, "Theme.wav", sine(1.0, RATE, 440.0, 0.3))
    _run(state, "Theme", "music")


# --- Then ----------------------------------------------------------------------------------------


@then("the game copy starts within 10 ms of the tone")
def _starts_on_tone(state: dict[str, Any]) -> None:
    samples, rate = read_wav_float(_game_copy(state, state["name"]))
    first_loud = int(np.argmax(np.abs(samples[:, 0]) > _TONE_THRESHOLD))
    assert first_loud / rate <= 0.010


@then("SourceArt/Audio/SFX/Chime.wav is byte-identical to the input")
def _source_identical(state: dict[str, Any]) -> None:
    stored = state["root"] / "SourceArt" / "Audio" / "SFX" / "Chime.wav"
    assert stored.read_bytes() == state["src"].read_bytes()


@then("the game copy is 1.5 s long within 10 ms")
def _cut_length(state: dict[str, Any]) -> None:
    samples, rate = read_wav_float(_game_copy(state, "Whoosh"))
    assert abs(samples.shape[0] / rate - 1.5) <= 0.010


@then("its last 20 ms fade to zero")
def _fades_to_zero(state: dict[str, Any]) -> None:
    samples, rate = read_wav_float(_game_copy(state, "Whoosh"))
    fade = round(0.020 * rate)
    assert samples[-1, 0] == 0.0
    assert np.abs(samples[-fade:, 0]).max() < np.abs(samples[-2 * fade : -fade, 0]).max()


@then(parsers.parse("the finished audio measures {target} LUFS within 1 LU"))
def _measures(state: dict[str, Any], target: str) -> None:
    if state["kind"] == "music":
        [encoded] = state["ffmpeg"].inputs
        samples, rate = _float_samples(encoded)
    else:
        samples, rate = read_wav_float(_game_copy(state, "Sample"))
    assert abs(integrated_loudness(samples, rate) - float(target)) <= 1.0


@then(
    "the step between the finished audio's last and first sample "
    "is no larger than its largest internal step"
)
def _seam_is_internal(state: dict[str, Any]) -> None:
    x = read_wav_float(_game_copy(state, "Loop"))[0][:, 0]
    assert abs(x[0] - x[-1]) <= np.abs(np.diff(x)).max()


@then("each game copy is byte-identical to the first one")
def _identical_to_first(state: dict[str, Any]) -> None:
    assert state["refinished"] is not None
    assert _game_copy(state, state["name"]).read_bytes() == state["first"]


@then(parsers.parse('SourceArt/Audio/audio.json records max_seconds {seconds} for "{name}"'))
def _records_cut(state: dict[str, Any], seconds: str, name: str) -> None:
    assert _stored_settings(state)[name]["max_seconds"] == float(seconds)


@then(parsers.parse('importing a different file as "{name}" fails with "{code}"'))
def _different_file_rejected(state: dict[str, Any], name: str, code: str) -> None:
    other = write_wav(state["saved"] / "other" / f"{name}.wav", sine(1.0, RATE, 330.0, 0.3), RATE)
    with pytest.raises(AudioError) as caught:
        import_audio(other, name, "sfx", godot=state["godot"])
    assert caught.value.code == code


@then(parsers.parse('it fails with "{code}" and a remediation line and no game copy exists'))
def _music_fails(state: dict[str, Any], code: str) -> None:
    assert state["error"] is not None and state["error"].code == code
    assert state["error"].remediation
    assert not _game_copy(state, "Theme", "music").exists()


@then("a sound-effect import still succeeds")
def _sfx_still_imports(state: dict[str, Any]) -> None:
    _save(state, "Chime.wav", sine(0.5, RATE, 440.0, 0.5))
    _run(state, "Chime", "sfx")
    assert state["error"] is None, state["error"]
    assert state["result"]["imported_to_godot"] is True


@then("the game copy is byte-identical to the stored WAV")
def _copy_is_stored(state: dict[str, Any]) -> None:
    stored = state["root"] / "SourceArt" / "Audio" / "SFX" / "Chime.wav"
    assert _game_copy(state, "Chime").read_bytes() == stored.read_bytes()


@then("SourceArt/Audio/audio.json records finish false")
def _records_unfinished(state: dict[str, Any]) -> None:
    assert _stored_settings(state)["Chime"]["finish"] is False
