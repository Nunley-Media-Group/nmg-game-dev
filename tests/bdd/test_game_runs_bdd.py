# ruff: noqa: E501  -- step decorators repeat the Gherkin text verbatim, so they run long.
"""pytest-bdd bindings for game_runs.feature: SCN001-SCN008, one per AC1-AC8 of #251.

The smoke run, the screenshot, the ship gate, and onboarding run through the real code with
``FakeGodotRunner``, the ship sandbox from ``tests/ship_fakes.py``, and a monkeypatched
``subprocess.run`` for the windowed screenshot argv, so no Godot process starts. The GDScript
behavior of NmgLaunch runs only inside ``scripts/run-godot-tests.sh``; SCN001 and SCN007 run that
gate with a fake Godot and check that it requires the ``test_nmg_launch.gd`` tests.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import stat
import struct
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.finalize import game_screenshot
from nmg_game_dev.godot import SubprocessGodotRunner
from nmg_game_dev.godot.__main__ import main as godot_main
from nmg_game_dev.godot.project import read_config
from nmg_game_dev.godot.runner import CommandResult
from nmg_game_dev.godot.smoke import smoke_args
from nmg_game_dev.onboard.godot import ensure_godot_project
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.ship.errors import ShipError
from tests.godot_fakes import FakeGodotRunner
from tests.ship_fakes import ShipSandbox, make_sandbox

FEATURE = "game_runs.feature"
REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "run-godot-tests.sh"
ADDON = REPO_ROOT / "plugins" / "nmg-game-dev-godot-addon" / "addons" / "nmg_game_dev"
LAUNCH_TESTS = ADDON / "tests" / "test_nmg_launch.gd"
PNG_1280x720 = (
    b"\x89PNG\r\n\x1a\n"
    + struct.pack(">I", 13)
    + b"IHDR"
    + struct.pack(">II", 1280, 720)
    + bytes([8, 6, 0, 0, 0])
    + b"\x00\x00\x00\x00"
)
_FAKE_GODOT_PY = r"""
import os, sys
args = sys.argv[1:]
if "--import" in args:
    sys.exit(0)
if any(arg.endswith("run_tests.gd") for arg in args):
    names = [name for name in os.environ.get("FAKE_PASS", "").split(",") if name]
    for name in names:
        print("PASS " + name)
    print(f"{len(names)} passed, 0 failed")
    sys.exit(0)
sys.exit(1)
"""
_OUTCOMES: dict[str, CommandResult] = {
    "prints a SCRIPT ERROR line": CommandResult(0, stdout="SCRIPT ERROR: Invalid call.\n"),
    "prints a Parse Error line": CommandResult(
        0, stdout="   Parse Error: Unexpected identifier.\n"
    ),
    "prints an ERROR: line": CommandResult(
        0, stdout="ERROR: Failed loading resource: res://a.glb\n"
    ),
    "exits 1": CommandResult(1, stdout="Godot Engine v4\n"),
    "does not exit within its timeout": CommandResult(
        124, stderr="Godot did not finish within 900 s and was stopped"
    ),
    "exits without writing the PNG": CommandResult(
        1, stdout="Godot Engine v4\n", stderr="ERROR: missing resource res://Crate.glb\n"
    ),
}


@pytest.fixture
def state(tmp_path: Path) -> dict[str, Any]:
    return {"tmp": tmp_path, "out": "", "err": "", "code": None, "runner": None}


def _project(root: Path) -> Path:
    project = root / "game" / "project.godot"
    project.parent.mkdir(parents=True, exist_ok=True)
    project.write_text("config_version=5\n", encoding="utf-8")
    return project


def _required_gate_tests() -> list[str]:
    return re.findall(r'"(test_\w+\.gd::\w+)"', GATE.read_text(encoding="utf-8"))


def _run_gate(root: Path, passing: Iterable[str]) -> subprocess.CompletedProcess[str]:
    """Run scripts/run-godot-tests.sh with a fake Godot that prints PASS for the ``passing`` tests."""
    root.mkdir(parents=True, exist_ok=True)
    fake_py = root / "fake_godot.py"
    fake_py.write_text(_FAKE_GODOT_PY, encoding="utf-8")
    fake = root / "godot"
    fake.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake_py}" "$@"\n', encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    env = {**os.environ, "GODOT_BIN": str(fake), "FAKE_PASS": ",".join(passing)}
    return subprocess.run(
        ["bash", str(GATE)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=180,
        cwd=REPO_ROOT,
    )


def _run_cli(state: dict[str, Any], argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    code = godot_main(argv, runner=state["runner"])
    captured = capsys.readouterr()
    state.update(code=code, out=captured.out, err=captured.err)


# SCN001 and SCN007: NmgLaunch behavior (GDScript, run through the gate) ----------------------


@given("the NmgLaunch autoload")
def _given_launch(state: dict[str, Any]) -> None:
    assert (ADDON / "nmg_launch.gd").is_file()
    assert "NmgLaunch" in (ADDON / "plugin.gd").read_text(encoding="utf-8")


@when(
    parsers.re(
        r'it is configured with the user arguments "(?P<args>[^"]*)" or the hash "(?P<url_hash>[^"]*)"$'
    )
)
def _when_configured_with_args_or_hash(state: dict[str, Any], args: str, url_hash: str) -> None:
    state["launch"] = (args, url_hash)


@when(parsers.re(r'it is configured with "(?P<args>[^"]*)"$'))
def _when_configured_with(state: dict[str, Any], args: str) -> None:
    state["launch"] = (args, "")


@then(
    'get_option "hour" is "12", get_option "at" is "Forest", "nmg-autoplay" reads "true", and an absent option returns its default'
)
def _then_options_read(state: dict[str, Any], tmp_path: Path) -> None:
    text = LAUNCH_TESTS.read_text(encoding="utf-8")
    for expected in ('"12"', '"Forest"', '"true"', '"#hour=12&at=Forest"'):
        assert expected in text, expected
    _assert_gate_requires(tmp_path, "test_nmg_launch.gd::test_cmdline_options")


@then('save_dir returns "user://nmg-test/", and without the flag it returns "user://"')
def _then_save_dir(state: dict[str, Any], tmp_path: Path) -> None:
    text = LAUNCH_TESTS.read_text(encoding="utf-8")
    assert '"user://nmg-test/"' in text and '"user://"' in text
    _assert_gate_requires(tmp_path, "test_nmg_launch.gd::test_save_dir_with_test_saves")


def _assert_gate_requires(root: Path, test: str) -> None:
    """The gate stops at the add-on step when ``test`` has no PASS line, and passes it otherwise."""
    names = _required_gate_tests()
    assert test in names, test
    missing = _run_gate(root / "missing", [name for name in names if name != test])
    assert missing.returncode == 5, missing.stderr
    assert test in missing.stderr
    present = _run_gate(root / "present", names)
    assert "add-on tests failed" not in present.stderr, present.stderr


# SCN002: the smoke run passes a clean game -------------------------------------------------------


@given("a consumer Godot project whose game run prints no error line and exits 0")
def _given_clean_game(state: dict[str, Any]) -> None:
    state["project"] = _project(state["tmp"])
    state["runner"] = FakeGodotRunner({"--fixed-fps": CommandResult(0, stdout="Godot Engine v4\n")})


@when(parsers.re(r'"(?P<command>python -m nmg_game_dev\.godot smoke[^"]*)" runs$'))
def _when_cli_runs(state: dict[str, Any], command: str, capsys: pytest.CaptureFixture[str]) -> None:
    argv = shlex.split(command)[3:]
    _run_cli(state, [argv[0], "--project", str(state["project"]), *argv[1:]], capsys)


@then(parsers.re(r'Godot ran with "(?P<args>[^"]+)" headless$'))
def _then_godot_ran_headless(state: dict[str, Any], args: str) -> None:
    assert state["runner"].calls == [smoke_args(600)]
    assert " ".join(smoke_args(600)) == args
    argv = SubprocessGodotRunner(Path("godot")).argv(smoke_args(600), project=Path("game"))
    assert "--headless" in argv


@then(parsers.re(r'the command prints "(?P<line>[^"]*)" and exits (?P<code>\d+)$'))
def _then_prints_and_exits(state: dict[str, Any], line: str, code: str) -> None:
    assert line in state["out"].splitlines()
    assert state["code"] == int(code), state["err"]


# SCN003: the smoke run fails on runtime errors --------------------------------------------------


@given(parsers.parse("a game run that {outcome}"))
def _given_game_run(state: dict[str, Any], outcome: str, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _OUTCOMES[outcome]
    state["runner"] = FakeGodotRunner({"--fixed-fps": result, "--": result})
    state["project"] = _project(state["tmp"])
    monkeypatch.chdir(state["tmp"])


@when("the smoke run runs")
def _when_smoke_runs(state: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    _run_cli(state, ["smoke", "--project", str(state["project"])], capsys)


@then(
    parsers.re(
        r'it exits 1 with "(?P<code>[^"]+)", at most 20 error lines, and a remediation line$'
    )
)
def _then_smoke_fails(state: dict[str, Any], code: str) -> None:
    assert state["code"] == 1
    assert f"ERROR [{code}]:" in state["err"]
    error_lines = [
        line
        for line in state["err"].splitlines()
        if line.startswith(("SCRIPT ERROR", "ERROR:")) or "Parse Error" in line
    ]
    assert len(error_lines) <= 20
    assert "Remediation:" in state["err"]


# SCN004: /ship gates on the smoke run ------------------------------------------------------------


@given(
    parsers.re(r'a ship of target "(?P<target>[^"]+)" whose smoke run prints a SCRIPT ERROR line$')
)
def _given_ship(state: dict[str, Any]) -> None:
    sandbox: ShipSandbox = make_sandbox(state["tmp"])
    (sandbox.game / "tests").mkdir()
    (sandbox.game / "tests" / "run_tests.gd").write_text("extends SceneTree\n", encoding="utf-8")
    sandbox.godot.responses["--fixed-fps"] = CommandResult(
        0, stdout="SCRIPT ERROR: Invalid call.\n"
    )
    state["sandbox"] = sandbox


@when("the ship runs")
def _when_ship_runs(state: dict[str, Any]) -> None:
    try:
        state["sandbox"].ship("all")
    except ShipError as error:
        state["ship_error"] = error


@then(parsers.re(r'it fails with "(?P<code>[^"]+)" after the project tests and no export runs$'))
def _then_ship_fails(state: dict[str, Any], code: str) -> None:
    sandbox: ShipSandbox = state["sandbox"]
    error = state["ship_error"]
    assert error.code == code
    commands = sandbox.godot_commands()
    assert commands.index(["-s", "res://tests/run_tests.gd"]) < commands.index(smoke_args(600))
    assert sandbox.exports() == []


@then(parsers.re(r'a dry run prints the smoke command with the "(?P<prefix>[^"]+)" prefix$'))
def _then_dry_run_prints(
    state: dict[str, Any], prefix: str, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    state["sandbox"].ship("all", dry_run=True)
    output = capsys.readouterr().out
    assert f"{prefix} godot --headless --audio-driver Dummy --path" in output
    assert "--fixed-fps 60 --quit-after 600 -- --nmg-autoplay --nmg-test-saves" in output


# SCN005: a screenshot is saved on demand --------------------------------------------------------


@given("a consumer Godot project whose game run writes a 1280x720 PNG")
def _given_png_game(state: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    state["project"] = _project(state["tmp"])
    state["argv"] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        state["argv"] = list(argv)
        for arg in argv:
            if arg.startswith("--nmg-shot="):
                Path(arg.removeprefix("--nmg-shot=")).write_bytes(PNG_1280x720)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr("nmg_game_dev.godot.runner.subprocess.run", fake_run)
    monkeypatch.setattr(
        "nmg_game_dev.godot.shot.resolve_godot", lambda env=None: Path("/fake/Godot")
    )
    monkeypatch.chdir(state["tmp"])


@when(
    parsers.re(
        r'"(?P<command>python -m nmg_game_dev\.godot shot[^"]*)" runs, or game_screenshot is called with the same values$'
    )
)
def _when_shot_or_tool(
    state: dict[str, Any], command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = shlex.split(command)[3:]
    _run_cli(state, [argv[0], *argv[1:2], "--project", str(state["project"]), *argv[2:]], capsys)
    state["cli_argv"] = list(state["argv"])
    state["tool"] = game_screenshot(
        "build/shots/forest.png",
        after=3,
        options=["--at=Forest", "--hour=18"],
        project_root=state["tmp"],
    )


@then(
    parsers.re(
        r'Godot ran without --headless with "(?P<args>[^"]+)", "--nmg-shot=<absolute path>", and "--nmg-shot-after=3"$'
    )
)
def _then_windowed(state: dict[str, Any], args: str) -> None:
    argv = state["cli_argv"]
    assert "--headless" not in argv
    for token in args.split():
        assert token in argv, token
    shot = next(arg for arg in argv if arg.startswith("--nmg-shot="))
    assert Path(shot.removeprefix("--nmg-shot=")).is_absolute()
    assert "--nmg-shot-after=3" in argv


@then("the result JSON has the path, width 1280, and height 720")
def _then_result_json(state: dict[str, Any]) -> None:
    for result in (json.loads(state["out"]), state["tool"]):
        assert result["path"].endswith("build/shots/forest.png")
        assert (result["width"], result["height"]) == (1280, 720)


# SCN006: a failed screenshot is reported --------------------------------------------------------


@when("the shot command runs")
def _when_shot_runs(state: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    _run_cli(state, ["shot", "build/shots/forest.png", "--project", str(state["project"])], capsys)


@then(parsers.re(r'it exits 1 with "(?P<code>[^"]+)" and the last lines of the game\'s output$'))
def _then_shot_fails(state: dict[str, Any], code: str) -> None:
    assert state["code"] == 1
    assert f"ERROR [{code}]:" in state["err"]
    assert "ERROR: missing resource res://Crate.glb" in state["err"]


@then(parsers.re(r'with no Godot binary it fails with "(?P<code>[^"]+)"$'))
def _then_no_godot(
    state: dict[str, Any],
    code: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _missing(env: Any = None, *args: Any, **kwargs: Any) -> Path:
        raise PipelineError(
            code="godot.not_found",
            message="Godot was not found.",
            remediation="Install Godot 4.",
            stage="godot",
        )

    monkeypatch.setattr("nmg_game_dev.godot.shot.resolve_godot", _missing)
    capsys.readouterr()
    code_no_godot = godot_main(
        ["shot", "build/shots/forest.png", "--project", str(state["project"])]
    )
    err = capsys.readouterr().err
    assert code_no_godot == 1
    assert f"ERROR [{code}]:" in err


# SCN008: onboarding registers the NmgLaunch autoload -------------------------------------------


@given("a consumer game/project.godot with only the NmgAssets autoload")
def _given_nmg_assets_only(state: dict[str, Any]) -> None:
    project = state["tmp"] / "game" / "project.godot"
    project.parent.mkdir(parents=True, exist_ok=True)
    project.write_text(
        'config_version=5\n\n[autoload]\n\nNmgAssets="*res://addons/nmg_game_dev/nmg_assets.gd"\n',
        encoding="utf-8",
    )
    state["project"] = project


@when("onboarding runs")
def _when_onboarding(state: dict[str, Any]) -> None:
    state["step"] = ensure_godot_project("godot_project", state["project"], "Game", refresh=False)


@then(
    '[autoload] holds NmgLaunch="*res://addons/nmg_game_dev/nmg_launch.gd" and the key is reported as refreshed'
)
def _then_autoload_refreshed(state: dict[str, Any]) -> None:
    config = read_config(state["project"])
    assert config[("autoload", "NmgLaunch")] == '"*res://addons/nmg_game_dev/nmg_launch.gd"'
    assert state["step"].status == "refreshed"


# Scenarios ---------------------------------------------------------------------------------------


@scenario(FEATURE, "Launch options read the same on desktop and web")
def test_scn001_launch_options_read_the_same_on_desktop_and_web() -> None:
    pass


@scenario(FEATURE, "The smoke run passes a clean game")
def test_scn002_the_smoke_run_passes_a_clean_game() -> None:
    pass


@scenario(FEATURE, "The smoke run fails on runtime errors")
def test_scn003_the_smoke_run_fails_on_runtime_errors() -> None:
    pass


@scenario(FEATURE, "/ship gates on the smoke run")
def test_scn004_ship_gates_on_the_smoke_run() -> None:
    pass


@scenario(FEATURE, "A screenshot is saved on demand")
def test_scn005_a_screenshot_is_saved_on_demand() -> None:
    pass


@scenario(FEATURE, "A failed screenshot is reported")
def test_scn006_a_failed_screenshot_is_reported() -> None:
    pass


@scenario(FEATURE, "Test runs use their own save folder")
def test_scn007_test_runs_use_their_own_save_folder() -> None:
    pass


@scenario(FEATURE, "Onboarding registers the NmgLaunch autoload")
def test_scn008_onboarding_registers_the_nmg_launch_autoload() -> None:
    pass
