"""Unit tests for ``python -m nmg_game_dev.godot`` (#251 FR3, FR4, AC2, AC5, AC6).

The CLI takes an injected ``FakeGodotRunner``, so no Godot process starts. A consumer project is a
``game/project.godot`` under ``CLAUDE_PROJECT_DIR`` or passed with ``--project``.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from nmg_game_dev.godot.__main__ import main
from nmg_game_dev.godot.runner import CommandResult
from nmg_game_dev.godot.smoke import smoke_args
from tests.godot_fakes import FakeGodotRunner


def _project(root: Path) -> Path:
    project = root / "game" / "project.godot"
    project.parent.mkdir(parents=True)
    project.write_text("config_version=5\n", encoding="utf-8")
    return project


def _png(width: int, height: int) -> bytes:
    ihdr = struct.pack(">II", width, height) + bytes([8, 6, 0, 0, 0])
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + b"\x00\x00\x00\x00"


def _shot_runner(width: int = 1280, height: int = 720) -> FakeGodotRunner:
    def run(args: list[str], project: Path) -> CommandResult:
        target = next(arg for arg in args if arg.startswith("--nmg-shot=")).removeprefix(
            "--nmg-shot="
        )
        Path(target).write_bytes(_png(width, height))
        return CommandResult(0)

    return FakeGodotRunner({"--": run})


def test_smoke_prints_the_frame_count_and_exits_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path)
    runner = FakeGodotRunner({"--fixed-fps": CommandResult(0)})
    code = main(["smoke", "--project", str(project)], runner=runner)
    assert code == 0
    assert capsys.readouterr().out.strip() == "smoke passed (600 frames)"
    assert runner.calls == [smoke_args(600)]


def test_smoke_frames_flag_is_passed_through(tmp_path: Path) -> None:
    runner = FakeGodotRunner({"--fixed-fps": CommandResult(0)})
    assert (
        main(["smoke", "--frames", "90", "--project", str(_project(tmp_path))], runner=runner) == 0
    )
    assert runner.calls == [smoke_args(90)]


def test_a_failed_smoke_prints_the_code_and_remediation_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeGodotRunner({"--fixed-fps": CommandResult(0, stdout="SCRIPT ERROR: boom\n")})
    code = main(["smoke", "--project", str(_project(tmp_path))], runner=runner)
    err = capsys.readouterr().err
    assert code == 1
    assert "ERROR [smoke.runtime_error]:" in err
    assert "SCRIPT ERROR: boom" in err
    assert "Remediation: Fix the first error above" in err


def test_a_smoke_without_a_project_is_godot_project_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["smoke", "--project", str(tmp_path / "absent" / "project.godot")], runner=FakeGodotRunner()
    )
    assert code == 1
    assert "ERROR [godot.project_missing]:" in capsys.readouterr().err


def test_smoke_rejects_zero_frames_with_exit_2(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as caught:
        main(
            ["smoke", "--frames", "0", "--project", str(_project(tmp_path))],
            runner=FakeGodotRunner(),
        )
    assert caught.value.code == 2


def test_launch_options_after_the_separator_are_refused_for_smoke(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as caught:
        main(
            ["smoke", "--project", str(_project(tmp_path)), "--", "--at=Forest"],
            runner=FakeGodotRunner(),
        )
    assert caught.value.code == 2


def test_shot_passes_the_launch_options_and_prints_the_result_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path)
    target = tmp_path / "build" / "shots" / "forest.png"
    runner = _shot_runner()
    code = main(
        [
            "shot",
            str(target),
            "--after",
            "3",
            "--project",
            str(project),
            "--",
            "--at=Forest",
            "--hour=18",
        ],
        runner=runner,
    )
    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {"path": str(target.absolute()), "width": 1280, "height": 720}
    call = runner.calls[0]
    assert call[:4] == ["--", "--at=Forest", "--hour=18", "--nmg-test-saves"]
    assert call[-1] == "--nmg-shot-after=3"
    assert f"--nmg-shot={target.absolute()}" in call


def test_shot_after_defaults_to_three_seconds(tmp_path: Path) -> None:
    runner = _shot_runner()
    main(["shot", str(tmp_path / "a.png"), "--project", str(_project(tmp_path))], runner=runner)
    assert runner.calls[0][-1] == "--nmg-shot-after=3"


def test_a_shot_that_writes_no_png_prints_shot_no_image_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeGodotRunner({"--": CommandResult(1, stderr="ERROR: bad resource\n")})
    code = main(
        ["shot", str(tmp_path / "a.png"), "--project", str(_project(tmp_path))], runner=runner
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "ERROR [shot.no_image]:" in err
    assert "ERROR: bad resource" in err
    assert "Remediation:" in err


def test_a_shot_without_a_project_is_godot_project_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["shot", str(tmp_path / "a.png"), "--project", str(tmp_path / "nope.godot")],
        runner=_shot_runner(),
    )
    assert code == 1
    assert "ERROR [godot.project_missing]:" in capsys.readouterr().err


def test_the_default_project_is_the_consumer_game_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    runner = FakeGodotRunner({"--fixed-fps": CommandResult(0)})
    assert main(["smoke"], runner=runner) == 0
    assert runner.projects == [tmp_path / "game"]
    assert "smoke passed (600 frames)" in capsys.readouterr().out


def test_an_unknown_command_is_an_argument_error() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["nonsense"], runner=FakeGodotRunner())
    assert caught.value.code == 2
