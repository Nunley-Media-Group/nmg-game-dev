"""The ``python -m nmg_game_dev.audio import`` CLI (#155 AC7, #249).

The CLI prints the result JSON on success and exits 0. A ``PipelineError`` prints
``ERROR [code] message`` and ``Remediation:`` to stderr and exits 1. Argument errors exit 2. The
tests call ``main`` in process; the ``wired`` fixture makes the fake Godot and ffmpeg runners the
defaults ``import_audio`` builds.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from nmg_game_dev.audio.__main__ import main
from nmg_game_dev.pipeline.errors import PipelineError
from tests.godot_fakes import FakeGodotRunner
from tests.unit.audio.conftest import FakeFfmpeg

Wired = tuple[FakeGodotRunner, FakeFfmpeg]


def test_import_prints_the_result_json_and_exits_zero(
    project: Path,
    source_file: Callable[[str], Path],
    wired: Wired,
    capsys: pytest.CaptureFixture[str],
) -> None:
    src = source_file("tone.wav")

    code = main(["import", "--file", str(src), "--name", "DoorCreak", "--kind", "sfx"])

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["imported_to_godot"] is True
    assert printed["godot_asset"] == "res://assets/Audio/DoorCreak.wav"
    assert printed["looping"] is False


def test_loop_flag_makes_the_music_loop(
    project: Path,
    source_file: Callable[[str], Path],
    wired: Wired,
    capsys: pytest.CaptureFixture[str],
) -> None:
    src = source_file("tone.mp3")

    code = main(
        ["import", "--file", str(src), "--name", "ForestTheme", "--kind", "music", "--loop"]
    )

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["looping"] is True
    assert printed["godot_asset"] == "res://assets/Audio/ForestTheme.ogg"
    sidecar = project / "game" / "assets" / "Audio" / "ForestTheme.ogg.import"
    assert "\nloop=true\n" in sidecar.read_text(encoding="utf-8")


def test_an_error_prints_code_and_remediation_and_exits_one(
    project: Path,
    source_file: Callable[[str], Path],
    wired: Wired,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(
        ["import", "--file", str(source_file("tone.wav")), "--name", "door", "--kind", "sfx"]
    )

    assert code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("ERROR [audio.invalid_request] ")
    assert "\nRemediation: " in captured.err
    assert wired[0].calls == []


def test_a_missing_godot_still_exits_zero_with_a_warning(
    project: Path,
    source_file: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _not_found() -> Path:
        raise PipelineError("godot.not_found", "Godot was not found.", "Install Godot 4", "godot")

    monkeypatch.setattr("nmg_game_dev.audio.core.resolve_godot", _not_found)

    code = main(
        ["import", "--file", str(source_file("tone.wav")), "--name", "DoorCreak", "--kind", "sfx"]
    )

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["imported_to_godot"] is False
    assert printed["warning"]["code"] == "godot.not_found"


def test_the_url_option_is_gone(project: Path, source_file: Callable[[str], Path]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(
            [
                "import",
                "--file",
                str(source_file("tone.wav")),
                "--name",
                "DoorCreak",
                "--kind",
                "sfx",
                "--url",
                "http://127.0.0.1:9999/mcp",
            ]
        )
    assert caught.value.code == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["import", "--name", "DoorCreak", "--kind", "sfx"],
        ["import", "--file", "x.wav", "--name", "DoorCreak", "--kind", "voice"],
        ["sing"],
        [],
    ],
    ids=["missing-file", "bad-kind-choice", "unknown-command", "no-command"],
)
def test_argument_errors_exit_two(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(argv)
    assert caught.value.code == 2


def test_the_module_runs_as_a_script(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "nmg_game_dev.audio", "import", "--help"],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "--kind" in result.stdout
    assert "--url" not in result.stdout
