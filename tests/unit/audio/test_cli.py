"""The ``python -m nmg_game_dev.audio import`` CLI (#155 AC7).

The CLI prints the result JSON on success and exits 0. A ``PipelineError`` prints
``ERROR [code] message`` and ``Remediation:`` to stderr and exits 1. Argument errors exit 2. The
tests call ``main`` in process, with the fake editor injected by the ``fake_unreal`` fixture.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from nmg_game_dev.audio.__main__ import main
from tests.unit.fake_unreal import FakeUnrealPythonClient


def test_import_prints_the_result_json_and_exits_zero(
    project: Path,
    source_file: Callable[[str], Path],
    fake_unreal: FakeUnrealPythonClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    src = source_file("tone.wav")

    code = main(["import", "--file", str(src), "--name", "DoorCreak", "--kind", "sfx"])

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["imported_to_unreal"] is True
    assert printed["unreal_asset"] == "/Game/Audio/SFX/SW_DoorCreak"
    assert printed["looping"] is False


def test_loop_flag_makes_the_soundwave_loop(
    project: Path,
    source_file: Callable[[str], Path],
    fake_unreal: FakeUnrealPythonClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    src = source_file("tone.mp3")

    code = main(
        ["import", "--file", str(src), "--name", "ForestTheme", "--kind", "music", "--loop"]
    )

    assert code == 0
    assert json.loads(capsys.readouterr().out)["looping"] is True
    sound = fake_unreal.editor.sound_wave("/Game/Audio/Music/SW_ForestTheme")
    assert sound is not None
    assert sound.get_editor_property("looping") is True


def test_an_error_prints_code_and_remediation_and_exits_one(
    project: Path,
    source_file: Callable[[str], Path],
    fake_unreal: FakeUnrealPythonClient,
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
    assert fake_unreal.codes == []


def test_an_unreachable_editor_still_exits_zero_with_a_warning(
    project: Path,
    source_file: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    unreachable = FakeUnrealPythonClient(reachable=False)
    monkeypatch.setattr(
        "nmg_game_dev.audio.__main__.UnrealMcpClient", lambda *_a, **_k: unreachable
    )
    monkeypatch.setattr("nmg_game_dev.audio.core.UnrealMcpClient", lambda *_a, **_k: unreachable)

    code = main(
        ["import", "--file", str(source_file("tone.wav")), "--name", "DoorCreak", "--kind", "sfx"]
    )

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["imported_to_unreal"] is False
    assert printed["warning"]["code"] == "mcp.unreal.unreachable"


def test_the_url_option_builds_a_client_for_that_endpoint(
    project: Path,
    source_file: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    fake = FakeUnrealPythonClient()

    def _factory(url: str | None = None, **_kwargs: object) -> FakeUnrealPythonClient:
        seen.append(str(url))
        return fake

    monkeypatch.setattr("nmg_game_dev.audio.__main__.UnrealMcpClient", _factory)

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

    assert seen == ["http://127.0.0.1:9999/mcp"]


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
