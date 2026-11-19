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


def test_no_loop_turns_a_stored_loop_off_and_omitting_it_keeps_the_stored_value(
    project: Path,
    source_file: Callable[[str], Path],
    wired: Wired,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = [
        "import",
        "--file",
        str(source_file("tone.wav")),
        "--name",
        "DoorCreak",
        "--kind",
        "sfx",
    ]

    assert main([*args, "--loop"]) == 0
    capsys.readouterr()
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["looping"] is True
    assert main([*args, "--no-loop"]) == 0
    assert json.loads(capsys.readouterr().out)["looping"] is False


def test_the_finishing_flags_reach_the_import_and_are_stored(
    project: Path,
    source_file: Callable[[str], Path],
    wired: Wired,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(
        [
            "import",
            "--file",
            str(source_file("tone.wav")),
            "--name",
            "DoorCreak",
            "--kind",
            "sfx",
            "--max-seconds",
            "0.1",
            "--loudness-lufs",
            "-14",
            "--loop-crossfade-ms",
            "120",
        ]
    )

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["settings"] == {
        "finish": True,
        "max_seconds": 0.1,
        "loudness_lufs": -14.0,
        "loop_crossfade_ms": 120,
    }
    assert printed["finish"]["loudness_lufs"] == pytest.approx(-14.0, abs=0.1)
    assert '"max_seconds": 0.1' in (project / "SourceArt/Audio/audio.json").read_text("utf-8")


def test_no_finish_imports_the_stored_wav_unchanged(
    project: Path,
    source_file: Callable[[str], Path],
    wired: Wired,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(
        [
            "import",
            "--file",
            str(source_file("tone.wav")),
            "--name",
            "DoorCreak",
            "--kind",
            "sfx",
            "--no-finish",
        ]
    )

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["finish"] == {"applied": False}
    assert printed["settings"]["finish"] is False
    stored = project / "SourceArt/Audio/SFX/DoorCreak.wav"
    assert (project / "game/assets/Audio/DoorCreak.wav").read_bytes() == stored.read_bytes()


def test_finish_turns_finishing_back_on_for_a_sound_stored_without_it(
    project: Path,
    source_file: Callable[[str], Path],
    wired: Wired,
    capsys: pytest.CaptureFixture[str],
) -> None:
    src = str(source_file("tone.wav"))
    base = ["import", "--file", src, "--name", "DoorCreak", "--kind", "sfx"]
    assert main([*base, "--no-finish"]) == 0
    capsys.readouterr()
    assert main(base) == 0
    assert json.loads(capsys.readouterr().out)["settings"]["finish"] is False

    code = main([*base, "--finish"])

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["finish"]["applied"] is True
    assert printed["settings"]["finish"] is True
    assert main(["refinish", "DoorCreak"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["finish"]["applied"] is True


def test_refinish_all_prints_the_list_and_exits_zero(
    project: Path,
    source_file: Callable[[str], Path],
    wired: Wired,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["import", "--file", str(source_file("tone.wav")), "--name", "DoorCreak", "--kind", "sfx"])
    capsys.readouterr()

    code = main(["refinish", "--all"])

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert [entry["name"] for entry in printed] == ["DoorCreak"]
    assert printed[0]["imported_to_godot"] is True


def test_refinish_takes_names_and_reports_an_unknown_one(
    project: Path,
    source_file: Callable[[str], Path],
    wired: Wired,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["import", "--file", str(source_file("tone.wav")), "--name", "DoorCreak", "--kind", "sfx"])
    capsys.readouterr()

    assert main(["refinish", "DoorCreak", "--project", str(project)]) == 0
    capsys.readouterr()

    code = main(["refinish", "Nope", "--project", str(project)])

    assert code == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("ERROR [audio.unknown_sound] ")
    assert "\nRemediation: " in captured.err


@pytest.mark.parametrize(
    "argv",
    [["refinish"], ["refinish", "--all", "DoorCreak"]],
    ids=["neither-all-nor-names", "both"],
)
def test_refinish_needs_exactly_one_of_all_or_names(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(argv)
    assert caught.value.code == 2


def test_refresh_prints_the_refreshed_tables_then_nothing_on_a_rerun(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """#237 AC3: refresh rewrites the Audio name table and a rerun changes nothing."""
    sound = project / "game" / "assets" / "Audio" / "DoorCreak.wav"
    sound.parent.mkdir(parents=True)
    sound.write_bytes(b"sound")
    table = project / "game" / "systems" / "Audio" / "audio_table.tres"
    table.parent.mkdir(parents=True)
    table.write_text(
        '[gd_resource type="Resource" script_class="NmgAudioTable" load_steps=2 format=3]\n',
        encoding="utf-8",
    )

    assert main(["refresh", "--project", str(project)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "refreshed_tables": ["game/systems/Audio/audio_table.tres"]
    }

    assert main(["refresh", "--project", str(project)]) == 0
    assert json.loads(capsys.readouterr().out) == {"refreshed_tables": []}


def test_refresh_without_a_godot_project_exits_one_with_the_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["refresh", "--project", str(tmp_path)])

    assert code == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("ERROR [audio.godot_project_missing] ")
    assert "\nRemediation: " in captured.err


def test_refresh_with_an_unreadable_backlog_prints_the_error_and_exits_one(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """#237 review F1: the CLI reports ``ERROR [code]`` and a remediation, not a traceback."""
    backlog = project / "docs" / "design" / "backlog.json"
    backlog.parent.mkdir(parents=True)
    backlog.write_text("{not json", encoding="utf-8")

    assert main(["refresh", "--project", str(project)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR [audio.backlog_invalid]" in captured.err
    assert "Remediation: " in captured.err
