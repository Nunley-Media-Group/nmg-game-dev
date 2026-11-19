"""Unit tests for the headless autoplay smoke run (#251 FR3, AC2, AC3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.godot.runner import TIMEOUT_EXIT, CommandResult
from nmg_game_dev.godot.smoke import (
    DEFAULT_FRAMES,
    MAX_ERROR_LINES,
    check_smoke,
    error_lines,
    run_smoke,
    smoke_args,
)
from nmg_game_dev.pipeline.errors import PipelineError
from tests.godot_fakes import FakeGodotRunner

_SMOKE = "--fixed-fps"  # FakeGodotRunner answers the smoke run by its first argument.


def _runner(result: CommandResult) -> FakeGodotRunner:
    return FakeGodotRunner({_SMOKE: result})


def test_smoke_args_run_600_frames_with_autoplay_and_test_saves() -> None:
    assert DEFAULT_FRAMES == 600
    assert smoke_args(600) == [
        "--fixed-fps",
        "60",
        "--quit-after",
        "600",
        "--",
        "--nmg-autoplay",
        "--nmg-test-saves",
    ]


def test_a_clean_run_passes_and_runs_the_smoke_args_once(tmp_path: Path) -> None:
    runner = _runner(CommandResult(0, stdout="Godot Engine v4\n"))
    result = run_smoke(runner, tmp_path)
    assert result.returncode == 0
    assert runner.calls == [smoke_args(DEFAULT_FRAMES)]
    assert runner.projects == [tmp_path]


def test_a_custom_frame_count_is_passed_through(tmp_path: Path) -> None:
    runner = _runner(CommandResult(0))
    run_smoke(runner, tmp_path, 120)
    assert runner.calls == [smoke_args(120)]
    assert runner.calls[0][3] == "120"


@pytest.mark.parametrize(
    "line",
    [
        "SCRIPT ERROR: Invalid call. Nonexistent function 'missing' in base 'Node'.",
        "   Parse Error: Unexpected identifier in class declaration.",
        "ERROR: Failed loading resource: res://Crate.glb",
    ],
)
def test_each_error_kind_fails_the_run_as_runtime_error(tmp_path: Path, line: str) -> None:
    runner = _runner(CommandResult(0, stdout=f"Godot Engine v4\n{line}\n"))
    with pytest.raises(PipelineError) as caught:
        run_smoke(runner, tmp_path)
    error = caught.value
    assert error.code == "smoke.runtime_error"
    assert error.stage == "smoke"
    assert line.strip() in error.message
    assert error.remediation.startswith("Fix the first error above")


def test_a_non_zero_exit_without_an_error_line_is_a_runtime_error(tmp_path: Path) -> None:
    runner = _runner(CommandResult(1, stdout="Godot Engine v4\n"))
    with pytest.raises(PipelineError) as caught:
        run_smoke(runner, tmp_path)
    assert caught.value.code == "smoke.runtime_error"
    assert "Godot exited 1" in caught.value.message


def test_a_run_past_its_timeout_is_smoke_timeout(tmp_path: Path) -> None:
    runner = _runner(
        CommandResult(TIMEOUT_EXIT, stderr="Godot did not finish within 900 s and was stopped")
    )
    with pytest.raises(PipelineError) as caught:
        run_smoke(runner, tmp_path)
    assert caught.value.code == "smoke.timeout"
    assert "did not finish" in caught.value.message
    assert caught.value.remediation


def test_at_most_twenty_error_lines_are_reported(tmp_path: Path) -> None:
    lines = "\n".join(f"ERROR: failure {index}" for index in range(25))
    runner = _runner(CommandResult(0, stdout=lines))
    with pytest.raises(PipelineError) as caught:
        run_smoke(runner, tmp_path)
    reported = [line for line in caught.value.message.splitlines() if "failure" in line]
    assert len(reported) == MAX_ERROR_LINES
    assert reported[0].endswith("failure 0")
    assert reported[-1].endswith("failure 19")


def test_error_lines_keep_order_and_strip_whitespace() -> None:
    result = CommandResult(0, stdout="  ERROR: first\nnoise\n", stderr="SCRIPT ERROR: second\n")
    assert error_lines(result) == ["ERROR: first", "SCRIPT ERROR: second"]


def test_an_error_word_in_the_middle_of_a_line_is_not_an_error_line() -> None:
    assert error_lines(CommandResult(0, stdout="note: ERROR: not a line start\n")) == []


def test_check_smoke_returns_for_a_clean_run() -> None:
    check_smoke(CommandResult(0, stdout="fine\n"))  # raises on a failed run; returns on a clean one
