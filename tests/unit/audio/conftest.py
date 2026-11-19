"""Shared fixtures for the audio import tests (#155, #249).

An autouse guard replaces Godot and ffmpeg resolution in the audio modules, so a test that forgets
to inject a fake fails instead of running a real binary. ``godot`` is a ``FakeGodotRunner`` whose
``probe_audio.gd`` answer is derived from the ``.import`` file the import wrote, the way Godot's
importer would read it. ``ffmpeg`` is a fake encoder that writes a stub Ogg file. The ``wired``
fixture makes both fakes the defaults, for the CLI tests that cannot inject them.
"""

from __future__ import annotations

import math
import shutil
import wave
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from nmg_game_dev.godot.project import parse_config
from nmg_game_dev.godot.runner import CommandResult
from tests.godot_fakes import FakeGodotRunner

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "audio"
OGG_STUB = b"OggS fake vorbis stream"

# The wav importer's edit/loop_mode option -> AudioStreamWAV.loop_mode (2 forward -> 1, else 0).
_WAV_LOOP_MODES = {"2": 1}


class FakeFfmpeg:
    """Records each ffmpeg call and writes a stub Ogg file at the output path.

    ``inputs`` keeps the bytes of each ``-i`` file at the time of the call, because the import
    deletes its scratch folder before the test can read it.
    """

    def __init__(self, result: CommandResult | None = None) -> None:
        self.calls: list[list[str]] = []
        self.inputs: list[bytes] = []
        self.result = result

    def run(self, args: Sequence[str]) -> CommandResult:
        argv = list(args)
        self.calls.append(argv)
        if "-i" in argv:
            self.inputs.append(Path(argv[argv.index("-i") + 1]).read_bytes())
        if self.result is not None:
            return self.result
        Path(argv[-1]).write_bytes(OGG_STUB)
        return CommandResult(0)


def sine(
    seconds: float, rate: int, freq: float = 1000.0, amplitude: float = 0.5, channels: int = 1
) -> np.ndarray:
    """Return (frames, channels) float samples of a sine, the same in every channel."""
    t = np.arange(round(seconds * rate)) / rate
    tone = amplitude * np.sin(2.0 * math.pi * freq * t)
    return np.repeat(tone[:, None], channels, axis=1)


def write_wav(path: Path, samples: np.ndarray, rate: int) -> Path:
    """Write (frames, channels) float samples in [-1, 1] as a 16-bit PCM WAV."""
    pcm = np.rint(np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(samples.shape[1])
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(pcm.tobytes())
    return path


def read_wav_float(path: Path) -> tuple[np.ndarray, int]:
    """Read a 16-bit PCM WAV back as (frames, channels) float samples in [-1, 1], and its rate."""
    with wave.open(str(path), "rb") as reader:
        channels = reader.getnchannels()
        rate = reader.getframerate()
        raw = reader.readframes(reader.getnframes())
    values = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    return values.reshape(-1, channels), rate


def _forbidden(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("audio tests must inject fake Godot and ffmpeg runners")


@pytest.fixture(autouse=True)
def _no_real_binaries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nmg_game_dev.audio.core.resolve_godot", _forbidden)
    monkeypatch.setattr("nmg_game_dev.audio.core.resolve_ffmpeg", _forbidden)
    monkeypatch.setattr("nmg_game_dev.audio.godot_import.resolve_ffmpeg", _forbidden)


def audio_probe(project: Path) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Answer ``probe_audio.gd`` from the ``.import`` file beside the probed stream."""

    def _answer(params: dict[str, Any]) -> dict[str, Any]:
        stream = project / str(params["stream"]).removeprefix("res://")
        config = parse_config(stream.with_name(stream.name + ".import").read_text("utf-8"))
        stream_type = config[("remap", "type")].strip('"')
        if stream_type == "AudioStreamWAV":
            mode = config[("params", "edit/loop_mode")]
            return {"class": stream_type, "loop_mode": _WAV_LOOP_MODES.get(mode, 0)}
        return {"class": stream_type, "loop": config[("params", "loop")] == "true"}

    return _answer


@pytest.fixture
def fixture_file() -> Callable[[str], Path]:
    """Return a path to a committed fixture clip by file name, e.g. ``tone.mp3``."""

    def _path(name: str) -> Path:
        return FIXTURES / name

    return _path


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project root with an empty ``game/project.godot`` that ``CLAUDE_PROJECT_DIR`` names."""
    root = tmp_path / "project"
    (root / "game").mkdir(parents=True)
    (root / "game" / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    return root


def fake_godot() -> FakeGodotRunner:
    """A fake headless Godot whose audio probe reads the ``.import`` files of its project."""
    runner = FakeGodotRunner()
    runner.responses["probe_audio.gd"] = lambda params: audio_probe(runner.projects[-1])(params)
    return runner


@pytest.fixture
def godot() -> FakeGodotRunner:
    return fake_godot()


@pytest.fixture
def ffmpeg() -> FakeFfmpeg:
    return FakeFfmpeg()


@pytest.fixture
def wired(
    monkeypatch: pytest.MonkeyPatch, godot: FakeGodotRunner, ffmpeg: FakeFfmpeg
) -> tuple[FakeGodotRunner, FakeFfmpeg]:
    """Make the fakes the runners ``import_audio`` builds when none is injected."""
    monkeypatch.setattr("nmg_game_dev.audio.core.resolve_godot", lambda: Path("/fake/godot"))
    monkeypatch.setattr("nmg_game_dev.audio.core.SubprocessGodotRunner", lambda _binary: godot)
    monkeypatch.setattr("nmg_game_dev.audio.core.resolve_ffmpeg", lambda: Path("/fake/ffmpeg"))
    monkeypatch.setattr("nmg_game_dev.audio.core.SubprocessFfmpegRunner", lambda _binary: ffmpeg)
    return godot, ffmpeg


@pytest.fixture
def source_file(tmp_path: Path, fixture_file: Callable[[str], Path]) -> Callable[[str], Path]:
    """Copy a fixture into a fresh folder outside the project, the way a saved download sits."""
    saved = tmp_path / "saved"
    saved.mkdir()

    def _copy(name: str) -> Path:
        target = saved / name
        shutil.copyfile(fixture_file(name), target)
        return target

    return _copy
