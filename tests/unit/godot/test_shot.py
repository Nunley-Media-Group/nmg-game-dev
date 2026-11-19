"""Unit tests for the on-demand game screenshot (#251 FR4, AC5, AC6)."""

from __future__ import annotations

import stat
import struct
from pathlib import Path

import pytest

from nmg_game_dev.godot.runner import CommandResult, SubprocessGodotRunner
from nmg_game_dev.godot.shot import NO_IMAGE_TAIL, SHOT_GRACE_S, png_size, shot_args, take_shot
from nmg_game_dev.pipeline.errors import PipelineError
from tests.godot_fakes import FakeGodotRunner


def _png(width: int, height: int) -> bytes:
    """A PNG header with an IHDR chunk; only the first 24 bytes are read."""
    ihdr = struct.pack(">II", width, height) + bytes([8, 6, 0, 0, 0])
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + b"\x00\x00\x00\x00"


def _writes_png(width: int, height: int) -> FakeGodotRunner:
    """A fake windowed Godot that writes a PNG to the path named by --nmg-shot."""

    def run(args: list[str], project: Path) -> CommandResult:
        target = next(arg for arg in args if arg.startswith("--nmg-shot=")).removeprefix(
            "--nmg-shot="
        )
        Path(target).write_bytes(_png(width, height))
        return CommandResult(0)

    return FakeGodotRunner({"--": run})


def test_shot_args_pass_options_then_the_shot_flags(tmp_path: Path) -> None:
    target = tmp_path / "forest.png"
    assert shot_args(target, 3, ["--at=Forest", "--hour=18"]) == [
        "--",
        "--at=Forest",
        "--hour=18",
        "--nmg-test-saves",
        f"--nmg-shot={target}",
        "--nmg-shot-after=3",
    ]


def test_a_saved_png_is_reported_with_its_size(tmp_path: Path) -> None:
    target = tmp_path / "build" / "shots" / "forest.png"
    runner = _writes_png(1280, 720)
    result = take_shot(tmp_path, target, 3, ["--at=Forest", "--hour=18"], runner=runner)
    assert result == {"path": str(target.absolute()), "width": 1280, "height": 720}
    assert runner.calls[0] == shot_args(target.absolute(), 3, ["--at=Forest", "--hour=18"])
    assert runner.timeouts == [3 + SHOT_GRACE_S]
    assert runner.projects == [tmp_path]


def test_a_relative_path_becomes_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = take_shot(tmp_path, Path("shots/a.png"), 0, [], runner=_writes_png(4, 2))
    assert result["path"] == str((tmp_path / "shots" / "a.png").absolute())


def test_a_stale_file_is_removed_before_the_run(tmp_path: Path) -> None:
    target = tmp_path / "old.png"
    target.write_bytes(_png(1, 1))
    seen: dict[str, bool] = {}

    def run(args: list[str], project: Path) -> CommandResult:
        seen["existed"] = target.exists()
        target.write_bytes(_png(2, 3))
        return CommandResult(0)

    result = take_shot(tmp_path, target, 1, [], runner=FakeGodotRunner({"--": run}))
    assert seen == {"existed": False}
    assert (result["width"], result["height"]) == (2, 3)


def test_no_png_is_shot_no_image_with_the_last_output_lines(tmp_path: Path) -> None:
    output = "".join(f"out-{index:02d}\n" for index in range(30))
    runner = FakeGodotRunner({"--": CommandResult(1, stdout=output)})
    with pytest.raises(PipelineError) as caught:
        take_shot(tmp_path, tmp_path / "a.png", 3, [], runner=runner)
    error = caught.value
    assert error.code == "shot.no_image"
    assert error.stage == "shot"
    assert "Godot exited 1" in error.message
    assert "out-29" in error.message
    assert "out-09" not in error.message
    assert sum(1 for line in error.message.splitlines() if line.startswith("out-")) == (
        NO_IMAGE_TAIL
    )
    assert "NmgLaunch" in error.remediation


def test_a_non_png_file_is_shot_no_image(tmp_path: Path) -> None:
    target = tmp_path / "a.png"

    def run(args: list[str], project: Path) -> CommandResult:
        target.write_bytes(b"not a png at all, just text")
        return CommandResult(0)

    with pytest.raises(PipelineError) as caught:
        take_shot(tmp_path, target, 3, [], runner=FakeGodotRunner({"--": run}))
    assert caught.value.code == "shot.no_image"


def test_a_negative_after_is_shot_invalid_after(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as caught:
        take_shot(tmp_path, tmp_path / "a.png", -1, [], runner=FakeGodotRunner())
    assert caught.value.code == "shot.invalid_after"


def test_a_missing_godot_is_godot_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _missing(env: object = None, *args: object, **kwargs: object) -> Path:
        raise PipelineError(
            code="godot.not_found",
            message="Godot was not found.",
            remediation="Install Godot 4.",
            stage="godot",
        )

    monkeypatch.setattr("nmg_game_dev.godot.shot.resolve_godot", _missing)
    with pytest.raises(PipelineError) as caught:
        take_shot(tmp_path, tmp_path / "a.png", 3, [], env={})
    assert caught.value.code == "godot.not_found"


def test_png_size_reads_the_ihdr_dimensions(tmp_path: Path) -> None:
    target = tmp_path / "a.png"
    target.write_bytes(_png(640, 360))
    assert png_size(target) == (640, 360)
    assert png_size(tmp_path / "absent.png") is None


def test_the_windowed_runner_argv_omits_headless(tmp_path: Path) -> None:
    binary = tmp_path / "godot"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    windowed = SubprocessGodotRunner(binary, headless=False).argv(
        ["--", "--nmg-shot=x"], project=tmp_path
    )
    assert "--headless" not in windowed
    assert windowed[1:5] == ["--audio-driver", "Dummy", "--path", str(tmp_path)]
    headless = SubprocessGodotRunner(binary).argv(["--import"], project=tmp_path)
    assert headless[1] == "--headless"
